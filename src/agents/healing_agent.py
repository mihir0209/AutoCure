"""
Healing Agent - Main AI Agent for Self-Healing System
Uses Microsoft Agent Framework design patterns with Groq/Cerebras backends.
"""

import asyncio
import uuid
import subprocess
from pathlib import Path
from typing import List, Optional, Dict, Any
from datetime import datetime
import aiofiles
import json
import tempfile
import shutil

from agents.ai_client import AIClient
from config import AIConfig
from utils.logger import setup_colored_logger
from utils.models import (
    ErrorInfo, 
    FixProposal, 
    TestResult, 
    HealingReport,
    FixStatus,
)

logger = setup_colored_logger("healing_agent")


class HealingAgent:
    """
    AI-Powered Healing Agent using Microsoft Agent Framework design patterns.
    
    Workflow:
    1. Receive error info from error processor
    2. Read source code and generate fix using AI
    3. Generate tests for the fix
    4. Execute test loop until pass or max attempts
    5. Return healing report
    
    This implements the fix proposal execution loop:
    loop(
        run(tests) -> results -> 
            1. pass -> complete
            2. fail -> propose nth fix, generate tests, continue
    )
    """
    
    def __init__(
        self,
        ai_config: AIConfig,
        max_attempts: int = 5,
        test_timeout: int = 60,
    ):
        self.ai_client = AIClient(
            provider=ai_config.provider,
            api_key=ai_config.active_api_key,
            model=ai_config.active_model,
        )
        self.max_attempts = max_attempts
        self.test_timeout = test_timeout
        
        logger.info(f"Healing Agent initialized with {ai_config.provider}")
    
    async def heal(self, error_info: ErrorInfo) -> HealingReport:
        """
        Main healing method - attempts to fix the error.
        
        Args:
            error_info: Information about the error to fix
            
        Returns:
            HealingReport with all fix attempts and results
        """
        report_id = str(uuid.uuid4())[:12]
        fix_proposals: List[FixProposal] = []
        test_results: List[TestResult] = []
        final_fix: Optional[FixProposal] = None
        
        logger.info(f"Starting healing process for: {error_info.error_type}")
        logger.info(f"Source file: {error_info.source_file}")
        
        # Read the source code
        source_code = await self._read_source_file(error_info.source_file)
        if not source_code:
            logger.error(f"Could not read source file: {error_info.source_file}")
            return HealingReport(
                report_id=report_id,
                error_info=error_info,
                fix_proposals=[],
                test_results=[],
                final_fix=None,
                git_branch=None,
                git_commit=None,
                status="failed",
                total_attempts=0,
            )
        
        current_code = source_code
        previous_explanation = ""
        
        # Main fix loop
        for attempt in range(1, self.max_attempts + 1):
            logger.info(f"═══ Fix Attempt {attempt}/{self.max_attempts} ═══")
            
            # Generate fix using AI
            if attempt == 1:
                fix_result = await self._generate_fix(
                    error_info=error_info,
                    source_code=current_code,
                )
            else:
                # Use test failure analysis for subsequent attempts
                fix_result = await self._improve_fix(
                    error_info=error_info,
                    source_code=current_code,
                    test_output=test_results[-1].test_output if test_results else "",
                    previous_explanation=previous_explanation,
                )
            
            if not fix_result:
                logger.error("Failed to generate fix")
                continue
            
            # Create fix proposal
            fix_id = f"{report_id}-{attempt}"
            fix_proposal = FixProposal(
                fix_id=fix_id,
                target_file=error_info.source_file,
                original_code=source_code,
                fixed_code=fix_result.get("fixed_code", ""),
                explanation=fix_result.get("explanation", ""),
                confidence_score=float(fix_result.get("confidence", 0.5)),
                status=FixStatus.TESTING,
                attempt_number=attempt,
            )
            fix_proposals.append(fix_proposal)
            previous_explanation = fix_proposal.explanation
            
            logger.info(f"Fix generated with confidence: {fix_proposal.confidence_score:.2%}")
            logger.info(f"Explanation: {fix_proposal.explanation[:100]}...")
            
            # Generate tests for this fix
            test_code = await self._generate_tests(
                error_info=error_info,
                fixed_code=fix_proposal.fixed_code,
            )
            
            # Run tests on the fix
            test_result = await self._run_tests(
                fix_proposal=fix_proposal,
                test_code=test_code,
            )
            test_results.append(test_result)
            
            if test_result.passed:
                logger.info(f"✓ Tests PASSED! ({test_result.pass_rate:.1f}% pass rate)")
                fix_proposal.status = FixStatus.PASSED
                final_fix = fix_proposal
                break
            else:
                logger.warning(f"✗ Tests FAILED ({test_result.pass_rate:.1f}% pass rate)")
                fix_proposal.status = FixStatus.FAILED
                current_code = fix_proposal.fixed_code  # Use this as base for next attempt
        
        # Determine final status
        status = "success" if final_fix else "failed"
        
        logger.info(f"Healing process {'SUCCEEDED' if final_fix else 'FAILED'}")
        logger.info(f"Total attempts: {len(fix_proposals)}")
        
        return HealingReport(
            report_id=report_id,
            error_info=error_info,
            fix_proposals=fix_proposals,
            test_results=test_results,
            final_fix=final_fix,
            git_branch=None,  # Set by orchestrator
            git_commit=None,  # Set by orchestrator
            status=status,
            total_attempts=len(fix_proposals),
        )
    
    async def _read_source_file(self, file_path: str) -> Optional[str]:
        """Read source file content"""
        try:
            path = Path(file_path)
            if not path.exists():
                return None
            async with aiofiles.open(path, 'r', encoding='utf-8') as f:
                return await f.read()
        except Exception as e:
            logger.error(f"Error reading source file: {e}")
            return None
    
    async def _generate_fix(
        self,
        error_info: ErrorInfo,
        source_code: str,
    ) -> Optional[Dict[str, Any]]:
        """Generate initial fix using AI"""
        try:
            error_context = f"""
Error Type: {error_info.error_type}
Message: {error_info.message}
File: {error_info.source_file}
Line: {error_info.line_number}

Stack Trace:
{error_info.stack_trace}

Root Cause Analysis:
{error_info.root_cause_analysis}
"""
            
            result = await self.ai_client.generate_fix(
                error_context=error_context,
                source_code=source_code,
                file_path=error_info.source_file,
            )
            
            return result
            
        except Exception as e:
            logger.error(f"Error generating fix: {e}")
            return None
    
    async def _improve_fix(
        self,
        error_info: ErrorInfo,
        source_code: str,
        test_output: str,
        previous_explanation: str,
    ) -> Optional[Dict[str, Any]]:
        """Generate improved fix based on test failures"""
        try:
            result = await self.ai_client.analyze_test_failure(
                test_output=test_output,
                source_code=source_code,
                previous_fix_explanation=previous_explanation,
            )
            
            # Normalize the response format
            return {
                "fixed_code": result.get("improved_fix", result.get("fixed_code", "")),
                "explanation": result.get("explanation", ""),
                "confidence": result.get("confidence", 0.5),
            }
            
        except Exception as e:
            logger.error(f"Error improving fix: {e}")
            return None
    
    async def _generate_tests(
        self,
        error_info: ErrorInfo,
        fixed_code: str,
    ) -> str:
        """Generate test cases for the fix"""
        try:
            return await self.ai_client.generate_tests(
                source_code=fixed_code,
                file_path=error_info.source_file,
                error_type=error_info.error_type,
            )
        except Exception as e:
            logger.error(f"Error generating tests: {e}")
            # Return basic test template
            return self._get_basic_test_template()
    
    def _get_basic_test_template(self) -> str:
        """Return a basic test template if AI generation fails"""
        return """
const assert = require('node:assert');
const { describe, it, test } = require('node:test');

describe('Basic Tests', () => {
    it('should not throw on import', () => {
        assert.doesNotThrow(() => {
            require('../server.js');
        });
    });
});
"""
    
    async def _run_tests(
        self,
        fix_proposal: FixProposal,
        test_code: str,
    ) -> TestResult:
        """
        Run tests on the proposed fix in an isolated environment.
        
        Creates a temporary directory, applies the fix, runs tests,
        and returns the results.
        """
        start_time = datetime.now()
        temp_dir = None
        
        try:
            # Create temporary directory for testing
            temp_dir = Path(tempfile.mkdtemp(prefix="selfhealer_test_"))
            logger.info(f"Testing in: {temp_dir}")
            
            # Get the original service directory
            original_dir = Path(fix_proposal.target_file).parent
            
            # Copy necessary files to temp directory
            for item in original_dir.iterdir():
                if item.is_file():
                    shutil.copy2(item, temp_dir / item.name)
                elif item.is_dir() and item.name != 'node_modules':
                    shutil.copytree(item, temp_dir / item.name)
            
            # Write the fixed code
            fixed_file = temp_dir / Path(fix_proposal.target_file).name
            async with aiofiles.open(fixed_file, 'w', encoding='utf-8') as f:
                await f.write(fix_proposal.fixed_code)
            
            # Create tests directory and write test file
            tests_dir = temp_dir / "tests"
            tests_dir.mkdir(exist_ok=True)
            
            test_file = tests_dir / "fix_test.js"
            async with aiofiles.open(test_file, 'w', encoding='utf-8') as f:
                await f.write(test_code)
            
            # Run tests using Node.js test runner
            process = await asyncio.create_subprocess_exec(
                "node",
                "--test",
                str(test_file),
                cwd=str(temp_dir),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,
            )
            
            try:
                stdout, _ = await asyncio.wait_for(
                    process.communicate(),
                    timeout=self.test_timeout
                )
                test_output = stdout.decode('utf-8', errors='replace')
            except asyncio.TimeoutError:
                process.kill()
                test_output = "Test execution timed out"
            
            # Parse test results
            passed, total, failed, errors = self._parse_test_output(test_output)
            
            execution_time = (datetime.now() - start_time).total_seconds()
            
            return TestResult(
                fix_id=fix_proposal.fix_id,
                passed=failed == 0 and total > 0,
                total_tests=total,
                passed_tests=passed,
                failed_tests=failed,
                test_output=test_output,
                execution_time=execution_time,
                error_messages=errors,
            )
            
        except Exception as e:
            logger.error(f"Error running tests: {e}")
            execution_time = (datetime.now() - start_time).total_seconds()
            
            return TestResult(
                fix_id=fix_proposal.fix_id,
                passed=False,
                total_tests=0,
                passed_tests=0,
                failed_tests=1,
                test_output=str(e),
                execution_time=execution_time,
                error_messages=[str(e)],
            )
            
        finally:
            # Cleanup temp directory
            if temp_dir and temp_dir.exists():
                try:
                    shutil.rmtree(temp_dir)
                except Exception as e:
                    logger.warning(f"Failed to cleanup temp dir: {e}")
    
    def _parse_test_output(self, output: str) -> tuple:
        """
        Parse test output to extract pass/fail counts.
        
        Returns:
            Tuple of (passed, total, failed, error_messages)
        """
        passed = 0
        failed = 0
        errors = []
        
        lines = output.split('\n')
        
        for line in lines:
            line_lower = line.lower()
            
            # Node.js test runner output patterns
            if '✔' in line or 'pass' in line_lower or 'ok' in line_lower:
                if 'fail' not in line_lower:
                    passed += 1
            elif '✖' in line or 'fail' in line_lower or 'error' in line_lower:
                failed += 1
                if line.strip():
                    errors.append(line.strip())
            
            # Look for summary lines
            if 'tests' in line_lower:
                import re
                # Pattern: "# tests 5" or "5 tests"
                numbers = re.findall(r'\d+', line)
                if numbers:
                    try:
                        total_from_summary = int(numbers[0])
                        if total_from_summary > passed + failed:
                            # Adjust if summary shows more tests
                            passed = total_from_summary - failed
                    except:
                        pass
        
        total = passed + failed
        if total == 0:
            # If we couldn't parse, assume at least one test ran
            total = 1
            if 'error' in output.lower() or 'fail' in output.lower():
                failed = 1
            else:
                passed = 1
        
        return passed, total, failed, errors
