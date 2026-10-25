"""
Regression Verifier & Auto-Rollback Engine (AutoCure Healing Module)
===================================================================
Automatically executes test suites on target codebases following
patch application. If tests fail, automatically rolls back file changes
and records detailed regression warnings.
"""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from .ast_patcher import ASTPatcher, ASTPatch

logger = logging.getLogger("regression_verifier")


@dataclass
class VerificationResult:
    """Result of running regression testing on an applied patch."""
    success: bool
    patch: ASTPatch
    tests_passed: bool
    regression_detected: bool
    rolled_back: bool
    exit_code: int
    test_output: str
    warning: Optional[str] = None
    duration_seconds: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """Convert verification result to dictionary for reporting and CI."""
        return {
            "success": self.success,
            "tests_passed": self.tests_passed,
            "regression_detected": self.regression_detected,
            "rolled_back": self.rolled_back,
            "exit_code": self.exit_code,
            "warning": self.warning,
            "duration_seconds": round(self.duration_seconds, 2),
            "patch": self.patch.to_dict() if self.patch else None,
            "metadata": self.metadata,
        }


class RegressionVerifier:
    """
    Validates patches by running the repository's test runner (pytest).
    Automatically rolls back file changes if regression or test failure occurs.
    """

    def __init__(
        self,
        patcher: Optional[ASTPatcher] = None,
        test_cmd: Optional[List[str]] = None,
        timeout: int = 120,
    ):
        self.patcher = patcher or ASTPatcher()
        self.test_cmd = test_cmd
        self.timeout = timeout

    def execute_tests(
        self, repo_path: str = "", test_target: Optional[str] = None
    ) -> Tuple[int, str, float]:
        """
        Run the test suite on the specified repository.
        Returns (exit_code, output_text, duration_seconds).
        """
        cwd = repo_path or self.patcher.repo_path or os.getcwd()
        cmd = list(self.test_cmd) if self.test_cmd else [sys.executable, "-m", "pytest"]

        if test_target:
            cmd.append(test_target)

        # Standard non-interactive test options
        if "-q" not in cmd and "-v" not in cmd:
            cmd.extend(["-v", "--tb=short"])

        start_time = time.monotonic()
        try:
            logger.info(f"Running test verification: {' '.join(cmd)} in {cwd}")
            proc = subprocess.run(
                cmd,
                cwd=cwd,
                capture_output=True,
                text=True,
                timeout=self.timeout,
            )
            duration = time.monotonic() - start_time
            output = proc.stdout + ("\n" + proc.stderr if proc.stderr else "")
            return proc.returncode, output.strip(), duration
        except subprocess.TimeoutExpired as e:
            duration = time.monotonic() - start_time
            logger.error(f"Test verification timed out after {self.timeout}s: {e}")
            out = (e.stdout or "") + ("\n" + (e.stderr or "") if e.stderr else "")
            return 124, f"TIMEOUT: Test suite exceeded {self.timeout}s limit.\n{out}", duration
        except Exception as e:
            duration = time.monotonic() - start_time
            logger.error(f"Failed to execute test runner: {e}")
            return 1, f"ERROR: Execution failure: {e}", duration

    def verify_and_heal(
        self,
        patch: ASTPatch,
        repo_path: str = "",
        test_target: Optional[str] = None,
        auto_rollback: bool = True,
    ) -> VerificationResult:
        """
        Apply patch, run test suite, and automatically rollback if regressions occur.
        """
        root_path = repo_path or self.patcher.repo_path

        # 1. Apply patch to disk with backup
        apply_ok = self.patcher.apply_patch(patch, repo_path=root_path, backup=True)
        if not apply_ok:
            warning = f"Failed to apply AST patch to {patch.file_path}:{patch.line_number}"
            logger.error(warning)
            return VerificationResult(
                success=False,
                patch=patch,
                tests_passed=False,
                regression_detected=False,
                rolled_back=False,
                exit_code=-1,
                test_output="Patch could not be applied to filesystem.",
                warning=warning,
            )

        # 2. Run test verification
        exit_code, test_output, duration = self.execute_tests(
            repo_path=root_path, test_target=test_target
        )

        tests_passed = (exit_code == 0)

        # 3. Handle success or regression
        if tests_passed:
            logger.info(
                f"✓ Regression check PASSED: patch at {patch.file_path}:{patch.line_number} "
                f"verified in {duration:.2f}s"
            )
            # Remove backup file on verified success
            full_path = self.patcher._resolve_file_path(patch.file_path, root_path)
            if full_path:
                bak_path = f"{full_path}.autocure_bak"
                if os.path.isfile(bak_path):
                    try:
                        os.remove(bak_path)
                    except Exception:
                        pass

            return VerificationResult(
                success=True,
                patch=patch,
                tests_passed=True,
                regression_detected=False,
                rolled_back=False,
                exit_code=exit_code,
                test_output=test_output,
                duration_seconds=duration,
            )
        else:
            # Regression / test failure
            regression_warning = (
                f"⚠️ Regression warning: Tests failed with exit code {exit_code} after applying "
                f"{patch.defect_type} patch to {patch.file_path}:{patch.line_number}. "
                f"{'Rolling back changes.' if auto_rollback else 'Changes retained (auto_rollback=False).'}"
            )
            logger.warning(regression_warning)

            rolled_back = False
            if auto_rollback:
                rolled_back = self.patcher.rollback_patch(patch, repo_path=root_path)

            return VerificationResult(
                success=False,
                patch=patch,
                tests_passed=False,
                regression_detected=True,
                rolled_back=rolled_back,
                exit_code=exit_code,
                test_output=test_output,
                warning=regression_warning,
                duration_seconds=duration,
            )
