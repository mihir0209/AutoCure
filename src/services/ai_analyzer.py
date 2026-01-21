"""
AI Analyzer Service for the Self-Healing Software System v2.0

Provides AI-powered analysis using Groq/Cerebras:
- Root cause analysis from error context and AST
- Fix proposals (not actual fixes, just suggestions)
- Code review for pull requests
"""

import asyncio
import json
import re
from typing import Optional, List, Dict, Any
from datetime import datetime
import aiohttp
from typing import Optional

from config import get_config
from utils.models import (
    DetectedError, ASTContext, RootCauseAnalysis, FixProposal,
    PRInfo, CodeReviewComment, CodeReviewResult, ErrorReplicationSummary
)
from utils.logger import setup_colored_logger


logger = setup_colored_logger("ai_analyzer")


class AIAnalyzer:
    """
    AI-powered analysis service using Groq or Cerebras.
    
    Features:
    - Root cause analysis with AST context
    - Fix proposal generation
    - Code review for PRs
    - Exponential backoff for rate limiting
    """
    
    def __init__(self, config = None):
        """
        Initialize the AI analyzer.
        
        Args:
            config: AI configuration (uses global config if not provided)
        """
        self.config = config or get_config().ai
        self.max_retries = 5
        self.base_delay = 1.0
        
    async def analyze_error(
        self, 
        error: DetectedError,
        source_code: Optional[str] = None,
        ast_context: Optional[ASTContext] = None,
        replication_summary: Optional[ErrorReplicationSummary] = None,
    ) -> RootCauseAnalysis:
        """
        Perform root cause analysis on a detected error.
        
        Args:
            error: The detected error
            source_code: Source code around the error location
            ast_context: AST context for the error
            replication_summary: Results from error replication
            
        Returns:
            Root cause analysis with fix proposals
        """
        # Build the prompt
        prompt = self._build_analysis_prompt(error, source_code, ast_context, replication_summary)
        
        # Call AI
        response = await self._call_ai(prompt, system_prompt=self._get_analysis_system_prompt())
        
        # Parse response
        analysis = self._parse_analysis_response(response, error)
        
        return analysis
    
    async def generate_fix_proposals(
        self,
        error: DetectedError,
        analysis: RootCauseAnalysis,
        source_code: str,
    ) -> List[FixProposal]:
        """
        Generate fix proposals for an error.
        
        Note: These are proposals only - not actual code changes.
        
        Args:
            error: The detected error
            analysis: Root cause analysis
            source_code: Source code to fix
            
        Returns:
            List of fix proposals
        """
        prompt = self._build_fix_prompt(error, analysis, source_code)
        
        response = await self._call_ai(prompt, system_prompt=self._get_fix_system_prompt())
        
        proposals = self._parse_fix_response(response, error)
        
        return proposals
    
    async def review_pull_request(
        self,
        pr_diff: Dict[str, Any],
        pr_info: PRInfo,
    ) -> CodeReviewResult:
        """
        Perform AI-powered code review on a pull request.
        
        Args:
            pr_diff: The PR diff data from GitHub
            pr_info: PR information
            
        Returns:
            Code review result with comments
        """
        prompt = self._build_review_prompt(pr_diff, pr_info)
        
        response = await self._call_ai(prompt, system_prompt=self._get_review_system_prompt())
        
        result = self._parse_review_response(response, pr_info)
        
        return result
    
    def _get_analysis_system_prompt(self) -> str:
        """Get the system prompt for error analysis."""
        return """You are an expert software engineer specializing in debugging and root cause analysis.
Your task is to analyze errors and determine their root cause.

When analyzing an error:
1. Examine the error message, stack trace, and source code
2. Consider the AST context to understand code structure
3. Look at replication patterns to understand error triggers
4. Identify the root cause - not just the symptom
5. Classify the error type and severity

Respond in JSON format with the following structure:
{
    "root_cause": "Clear explanation of the root cause",
    "error_category": "null_reference|type_error|logic_error|validation_error|other",
    "severity": "critical|high|medium|low",
    "affected_components": ["list", "of", "affected", "components"],
    "confidence": 0.0-1.0,
    "additional_context": "Any additional relevant context"
}"""
    
    def _get_fix_system_prompt(self) -> str:
        """Get the system prompt for fix generation."""
        return """You are an expert software engineer specializing in bug fixes.
Your task is to propose fixes for software bugs.

IMPORTANT: You are proposing fixes, not implementing them. The user will decide whether to apply them.

For each fix proposal:
1. Describe the change clearly
2. Explain why this fix addresses the root cause
3. List any potential side effects
4. Suggest any related changes that might be needed

Respond in JSON format with an array of proposals:
{
    "proposals": [
        {
            "title": "Brief title of the fix",
            "description": "Detailed description of what to change",
            "code_suggestion": "Pseudo-code or code snippet showing the fix",
            "file_path": "path/to/file",
            "line_range": [start_line, end_line],
            "confidence": 0.0-1.0,
            "potential_side_effects": ["list", "of", "side", "effects"],
            "testing_suggestions": ["how", "to", "verify", "the", "fix"]
        }
    ]
}"""
    
    def _get_review_system_prompt(self) -> str:
        """Get the system prompt for code review."""
        return """You are an expert code reviewer focused on code quality, security, and best practices.
Your task is to review pull request changes and provide constructive feedback.

When reviewing code:
1. Look for bugs, edge cases, and potential issues
2. Check for security vulnerabilities
3. Evaluate code style and readability
4. Suggest improvements and optimizations
5. Note any missing tests or documentation

Be constructive and specific. Reference line numbers when possible.

Respond in JSON format:
{
    "overall_assessment": "approve|request_changes|comment",
    "summary": "Brief summary of the review",
    "comments": [
        {
            "file": "path/to/file",
            "line": 42,
            "severity": "critical|warning|suggestion|nitpick",
            "category": "bug|security|performance|style|documentation",
            "comment": "The actual review comment",
            "suggestion": "Optional code suggestion"
        }
    ],
    "highlights": ["List of good things about the PR"]
}"""
    
    def _build_analysis_prompt(
        self, 
        error: DetectedError,
        source_code: Optional[str],
        ast_context: Optional[ASTContext],
        replication_summary: Optional[ErrorReplicationSummary],
    ) -> str:
        """Build the prompt for error analysis."""
        
        parts = [
            "## Error Analysis Request",
            "",
            "### Error Details",
            f"- **Type**: {error.error_type}",
            f"- **Category**: {error.error_category}",
            f"- **Message**: {error.message}",
            f"- **File**: {error.source_file}",
            f"- **Line**: {error.line_number}",
            f"- **Function**: {error.function_name or 'Unknown'}",
            f"- **Language**: {error.language}",
        ]
        
        if error.stack_trace:
            parts.extend([
                "",
                "### Stack Trace",
                "```",
                error.stack_trace[:2000],
                "```",
            ])
        
        if error.api_endpoint:
            parts.extend([
                "",
                "### API Context",
                f"- **Endpoint**: {error.http_method} {error.api_endpoint}",
                f"- **Payload**: {json.dumps(error.payload)[:500] if error.payload else 'None'}",
            ])
        
        if source_code:
            parts.extend([
                "",
                "### Source Code",
                "```",
                source_code[:3000],
                "```",
            ])
        
        if ast_context:
            parts.extend([
                "",
                "### AST Context",
            ])
            if ast_context.parent_function:
                parts.append(f"- **Parent Function**: {ast_context.parent_function.name}")
            if ast_context.parent_class:
                parts.append(f"- **Parent Class**: {ast_context.parent_class.name}")
        
        if replication_summary:
            parts.extend([
                "",
                "### Error Replication Results",
                f"- **Reproducible**: {replication_summary.is_reproducible}",
                f"- **Reproduction Rate**: {replication_summary.reproduction_rate:.0%}",
            ])
            if replication_summary.error_patterns:
                parts.append("- **Patterns**:")
                for pattern in replication_summary.error_patterns:
                    parts.append(f"  - {pattern}")
        
        parts.extend([
            "",
            "Please analyze this error and provide the root cause analysis in JSON format.",
        ])
        
        return "\n".join(parts)
    
    def _build_fix_prompt(
        self,
        error: DetectedError,
        analysis: RootCauseAnalysis,
        source_code: str,
    ) -> str:
        """Build the prompt for fix generation."""
        
        return f"""## Fix Proposal Request

### Error
- **Type**: {error.error_type}
- **Message**: {error.message}
- **File**: {error.source_file}:{error.line_number}

### Root Cause Analysis
{analysis.root_cause}

### Severity: {analysis.severity}

### Source Code
```
{source_code[:4000]}
```

Please propose fixes for this error. Remember: propose only, do not implement.
Respond in JSON format with an array of proposals."""
    
    def _build_review_prompt(
        self,
        pr_diff: Dict[str, Any],
        pr_info: PRInfo,
    ) -> str:
        """Build the prompt for code review."""
        
        files_summary = []
        for f in pr_diff.get("files", [])[:10]:  # Limit to 10 files
            files_summary.append(f"- {f['filename']} (+{f['additions']}/-{f['deletions']})")
        
        # Build diff excerpt (limit size)
        diff_excerpt = pr_diff.get("diff", "")[:8000]
        
        return f"""## Pull Request Code Review

### PR Information
- **Title**: {pr_diff.get('title', pr_info.title)}
- **Author**: {pr_diff.get('author', 'Unknown')}
- **Base Branch**: {pr_diff.get('base_branch', pr_info.base_branch)}
- **Head Branch**: {pr_diff.get('head_branch', pr_info.head_branch)}

### Description
{pr_diff.get('description', 'No description provided')[:1000]}

### Files Changed ({pr_diff.get('changed_files', 0)} files)
{chr(10).join(files_summary)}

### Diff
```diff
{diff_excerpt}
```

Please review this pull request and provide feedback in JSON format."""
    
    async def _call_ai(
        self, prompt: str, system_prompt: str = ""
    ) -> str:
        """
        Call the AI API with exponential backoff for rate limiting.
        """
        headers = {
            "Authorization": f"Bearer {self.config.active_api_key}",
            "Content-Type": "application/json",
        }
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": self.config.active_model,
            "messages": messages,
            "temperature": 0.3,
            "max_tokens": 4000,
        }
        
        delay = self.base_delay
        
        for attempt in range(self.max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        f"{self.config.active_base_url}/chat/completions",
                        headers=headers,
                        json=payload,
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            content = data["choices"][0]["message"]["content"]
                            
                            # Strip <think> tags if present
                            content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
                            
                            return content.strip()
                        
                        elif response.status == 429:
                            # Rate limited - exponential backoff
                            logger.warning(f"Rate limited, waiting {delay}s...")
                            await asyncio.sleep(delay)
                            delay *= 2
                            continue
                        
                        else:
                            error_text = await response.text()
                            logger.error(f"AI API error {response.status}: {error_text}")
                            
            except Exception as e:
                logger.error(f"AI API call failed: {e}")
                if attempt < self.max_retries - 1:
                    await asyncio.sleep(delay)
                    delay *= 2
        
        return "{}"  # Return empty JSON on failure
    
    def _parse_analysis_response(
        self, response: str, error: DetectedError
    ) -> RootCauseAnalysis:
        """Parse the AI response into a RootCauseAnalysis."""
        
        try:
            # Try to extract JSON from response
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = {}
        except json.JSONDecodeError:
            logger.warning("Failed to parse AI response as JSON")
            data = {}
        
        return RootCauseAnalysis(
            error=error,
            root_cause=data.get("root_cause", "Unable to determine root cause"),
            error_category=data.get("error_category", "unknown"),
            severity=data.get("severity", "medium"),
            affected_components=data.get("affected_components", []),
            confidence=data.get("confidence", 0.5),
            additional_context=data.get("additional_context", ""),
            analyzed_at=datetime.utcnow(),
        )
    
    def _parse_fix_response(
        self, response: str, error: DetectedError
    ) -> List[FixProposal]:
        """Parse the AI response into FixProposals."""
        
        proposals = []
        
        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                data = json.loads(json_match.group())
                raw_proposals = data.get("proposals", [])
            else:
                raw_proposals = []
        except json.JSONDecodeError:
            logger.warning("Failed to parse fix response as JSON")
            raw_proposals = []
        
        for p in raw_proposals:
            proposals.append(FixProposal(
                error=error,
                title=p.get("title", "Untitled Fix"),
                description=p.get("description", ""),
                code_suggestion=p.get("code_suggestion", ""),
                file_path=p.get("file_path", error.source_file),
                line_range=tuple(p.get("line_range", [error.line_number, error.line_number])),
                confidence=p.get("confidence", 0.5),
                potential_side_effects=p.get("potential_side_effects", []),
                testing_suggestions=p.get("testing_suggestions", []),
            ))
        
        return proposals
    
    def _parse_review_response(
        self, response: str, pr_info: PRInfo
    ) -> CodeReviewResult:
        """Parse the AI response into a CodeReviewResult."""
        
        try:
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                data = json.loads(json_match.group())
            else:
                data = {}
        except json.JSONDecodeError:
            logger.warning("Failed to parse review response as JSON")
            data = {}
        
        comments = []
        for c in data.get("comments", []):
            comments.append(CodeReviewComment(
                file_path=c.get("file", ""),
                line_number=c.get("line"),
                severity=c.get("severity", "suggestion"),
                category=c.get("category", "general"),
                comment=c.get("comment", ""),
                suggestion=c.get("suggestion"),
            ))
        
        return CodeReviewResult(
            pr_info=pr_info,
            overall_assessment=data.get("overall_assessment", "comment"),
            summary=data.get("summary", "Review completed"),
            comments=comments,
            highlights=data.get("highlights", []),
            reviewed_at=datetime.utcnow(),
        )


# Singleton instance
_analyzer: Optional[AIAnalyzer] = None


def get_ai_analyzer() -> AIAnalyzer:
    """Get or create the AI analyzer singleton."""
    global _analyzer
    if _analyzer is None:
        _analyzer = AIAnalyzer()
    return _analyzer
