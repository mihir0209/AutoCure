"""
AI Analyzer Service for the Self-Healing Software System v2.0

Provides AI-powered analysis using Groq/Cerebras:
- Deep root cause analysis from error context, AST, and replication data
- Exact fix proposal generation (precise code diffs, not vague advice)
- Code review for pull requests
- Robust JSON extraction with fallback parsing
"""

import asyncio
import json
import re
from typing import Optional, List, Dict, Any
from datetime import datetime
import aiohttp

from config import get_config
from utils.models import (
    DetectedError, ASTContext, RootCauseAnalysis, FixProposal,
    PRInfo, CodeReviewComment, CodeReviewResult, ErrorReplicationSummary
)
from utils.logger import setup_colored_logger


logger = setup_colored_logger("ai_analyzer")


# ════════════════════════════════════════════════════════════════
#  Helpers
# ════════════════════════════════════════════════════════════════

def _extract_json(text: str) -> dict:
    """
    Robustly extract the first JSON object from an AI response.
    Handles markdown fences, preamble text, trailing commas, etc.
    """
    if not text:
        return {}

    # Strip <think>...</think> tags (DeepSeek / reasoning models)
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()

    # Strip markdown code fences
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'```\s*$', '', text, flags=re.MULTILINE)

    # Try direct parse first
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Find the outermost { ... }
    depth = 0
    start = None
    for i, ch in enumerate(text):
        if ch == '{':
            if depth == 0:
                start = i
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0 and start is not None:
                candidate = text[start:i + 1]
                # Remove trailing commas before } or ]
                candidate = re.sub(r',\s*([}\]])', r'\1', candidate)
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    pass  # keep looking

    return {}


class AIAnalyzer:
    """
    AI-powered analysis service using Groq or Cerebras.

    Features:
    - Root cause analysis with AST context
    - Exact fix proposal generation (concrete code, not just advice)
    - Code review for PRs
    - Exponential backoff for rate limiting
    - Robust JSON extraction from AI responses
    """

    def __init__(self, config=None):
        self.config = config or get_config().ai
        self.max_retries = self.config.max_retries
        self.base_delay = self.config.initial_retry_delay

    # ──────────────────────────────────────────────────────────
    #  Public API
    # ──────────────────────────────────────────────────────────

    async def analyze_error(
        self,
        error: DetectedError,
        source_code: Optional[str] = None,
        ast_context=None,
        replication_summary: Optional[ErrorReplicationSummary] = None,
        user_id: str = "",
    ) -> RootCauseAnalysis:
        """Perform root cause analysis on a detected error."""
        prompt = self._build_analysis_prompt(error, source_code, ast_context, replication_summary)
        response = await self._call_ai(prompt, system_prompt=self._get_analysis_system_prompt())
        return self._parse_analysis_response(response, error)

    async def generate_fix_proposals(
        self,
        error: DetectedError,
        analysis: RootCauseAnalysis,
        source_code: str,
        user_id: str = "",
    ) -> List[FixProposal]:
        """
        Generate *exact* fix proposals — concrete code that can be applied.
        These are suggestions only; the user decides whether to apply them.
        """
        prompt = self._build_fix_prompt(error, analysis, source_code)
        response = await self._call_ai(prompt, system_prompt=self._get_fix_system_prompt())
        return self._parse_fix_response(response, error)

    async def review_pull_request(
        self,
        pr_diff: Dict[str, Any],
        pr_info: PRInfo,
        user_id: str = "",
    ) -> CodeReviewResult:
        """Perform AI-powered code review on a pull request."""
        prompt = self._build_review_prompt(pr_diff, pr_info)
        response = await self._call_ai(prompt, system_prompt=self._get_review_system_prompt())
        return self._parse_review_response(response, pr_info)

    # ══════════════════════════════════════════════════════════
    #  System Prompts (hardened for precision)
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def _get_analysis_system_prompt() -> str:
        return """You are an expert software debugging engineer. Your task is to analyse an error report and determine the **exact** root cause — not symptoms.

RULES:
1. Read the error message, AST context, code, and replication data carefully.
2. Pinpoint the EXACT line(s) and variable(s) causing the issue.
3. Classify the category precisely (one of: null_reference, type_error, attribute_error, key_error, index_error, import_error, syntax_error, logic_error, validation_error, concurrency_error, network_error, permission_error, configuration_error, dependency_error, other).
4. Severity must be one of: critical, high, medium, low.
5. Confidence is 0.0-1.0 reflecting how certain you are.
6. affected_components must list specific functions/classes/modules.

Respond ONLY with valid JSON (no markdown, no explanation outside the JSON):
{
  "root_cause": "<precise 1-3 sentence explanation referencing exact variable/function/line>",
  "error_category": "<category>",
  "severity": "<severity>",
  "affected_components": ["module.Class.method", "..."],
  "confidence": 0.85,
  "additional_context": "<any extra insight>"
}"""

    @staticmethod
    def _get_fix_system_prompt() -> str:
        return """You are an expert software engineer. Your task is to propose **exact, copy-paste-ready** code fixes.

RULES:
1. Each proposal must contain the EXACT original code AND the EXACT replacement code.
2. The replacement must be syntactically valid and semantically correct.
3. Keep fixes minimal — change only what is necessary.
4. Explain WHY the fix works in 1-2 sentences.
5. Rate risk_level as "low" (safe refactor), "medium" (behaviour change), or "high" (structural change).
6. List concrete side_effects (empty list if none).
7. Confidence 0.0-1.0 reflects certainty the fix resolves the issue.

Respond ONLY with valid JSON (no markdown):
{
  "proposals": [
    {
      "target_file": "path/to/file.py",
      "line_number": 42,
      "original_code": "exact original code to replace (multi-line ok)",
      "suggested_code": "exact replacement code (multi-line ok)",
      "explanation": "Why this fixes the issue",
      "risk_level": "low|medium|high",
      "confidence": 0.9,
      "side_effects": ["list of side effects or empty"]
    }
  ]
}"""

    @staticmethod
    def _get_review_system_prompt() -> str:
        return """You are an expert code reviewer focusing on correctness, security, and best practices.

RULES:
1. Reference exact file paths and line numbers.
2. severity: one of "critical", "warning", "suggestion", "info".
3. comment_type: one of "bug", "security", "performance", "style", "documentation", "best_practice".
4. overall_assessment: one of "approve", "request_changes", "comment".
5. Provide a concrete suggested_fix when possible.
6. highlights: list genuinely good things about the code.

Respond ONLY with valid JSON:
{
  "overall_assessment": "approve|request_changes|comment",
  "summary": "Brief summary",
  "comments": [
    {
      "file_path": "path/to/file",
      "line_number": 42,
      "severity": "critical|warning|suggestion|info",
      "comment_type": "bug|security|performance|style|documentation|best_practice",
      "message": "Detailed comment",
      "suggested_fix": "optional code suggestion"
    }
  ],
  "highlights": ["good thing 1", "good thing 2"]
}"""

    # ══════════════════════════════════════════════════════════
    #  Prompt Builders
    # ══════════════════════════════════════════════════════════

    def _build_analysis_prompt(
        self,
        error: DetectedError,
        source_code: Optional[str],
        ast_context,
        replication_summary: Optional[ErrorReplicationSummary],
    ) -> str:
        parts = [
            "## Error Analysis Request\n",
            "### Error Details",
            f"- **Type**: {error.error_type}",
            f"- **Category**: {error.error_category}",
            f"- **Message**: {error.message}",
            f"- **File**: {error.source_file}",
            f"- **Line**: {error.line_number}",
            f"- **Function**: {error.function_name or 'Unknown'}",
            f"- **Language**: {error.language}",
            f"- **Severity**: {error.severity}",
        ]

        if error.stack_trace:
            parts += ["", "### Stack Trace", "```", error.stack_trace[:3000], "```"]

        if error.api_endpoint:
            payload_str = json.dumps(error.payload, default=str)[:800] if error.payload else "None"
            parts += [
                "", "### API Context",
                f"- **Endpoint**: {error.http_method} {error.api_endpoint}",
                f"- **Payload**: {payload_str}",
            ]

        if source_code:
            parts += ["", "### Source Code (around error location)", "```", source_code[:5000], "```"]

        # AST context — can be a pre-built string (from build_ai_context) or an ASTContext model
        if ast_context:
            parts.append("\n### AST Context")
            if isinstance(ast_context, str):
                parts.append(ast_context[:6000])
            elif hasattr(ast_context, 'error_node'):
                if ast_context.error_node:
                    n = ast_context.error_node
                    parts.append(f"- **Error Node**: `{n.node_type}` → `{n.name}` (L{n.start_line}-{n.end_line})")
                    if n.code_snippet:
                        parts += ["```", n.code_snippet[:500], "```"]
                for pn in reversed(getattr(ast_context, 'parent_nodes', [])):
                    nt = pn.node_type.lower()
                    if any(kw in nt for kw in ("function", "method", "def")):
                        parts.append(f"- **Enclosing Function**: `{pn.name}` (L{pn.start_line})")
                        break
                for pn in reversed(getattr(ast_context, 'parent_nodes', [])):
                    if "class" in pn.node_type.lower():
                        parts.append(f"- **Enclosing Class**: `{pn.name}` (L{pn.start_line})")
                        break
                imports = getattr(ast_context, 'file_imports', [])
                if imports:
                    parts.append(f"- **Imports**: {', '.join(imports[:20])}")

        if replication_summary:
            parts += [
                "", "### Error Replication Results",
                f"- **Reproducible**: {replication_summary.is_reproducible}",
                f"- **Reproduction Rate**: {replication_summary.reproduction_rate:.0%}",
                f"- **Total Attempts**: {len(replication_summary.results)}",
            ]
            if replication_summary.error_patterns:
                parts.append("- **Patterns**:")
                for pattern in replication_summary.error_patterns[:8]:
                    parts.append(f"  - {pattern}")

        parts.append("\nAnalyse this error and respond with JSON only.")
        return "\n".join(parts)

    def _build_fix_prompt(
        self,
        error: DetectedError,
        analysis: RootCauseAnalysis,
        source_code: str,
    ) -> str:
        return f"""## Fix Proposal Request

### Error
- **Type**: {error.error_type}
- **Message**: {error.message}
- **File**: {error.source_file}:{error.line_number}
- **Language**: {error.language}

### Root Cause (from prior analysis)
{analysis.root_cause}

### Error Category: {analysis.error_category}
### Severity: {analysis.severity}
### Affected Components: {', '.join(analysis.affected_components) if analysis.affected_components else 'Unknown'}

### Source Code
```
{source_code[:6000]}
```

Generate EXACT fix proposals. Each proposal must have the original code snippet and the corrected replacement. Focus on:
1. The minimal change that fixes the root cause
2. Defensive guards if the issue is a missing null/undefined check
3. Correct types/imports if the issue is a type or import error

Respond with JSON only."""

    def _build_review_prompt(
        self,
        pr_diff: Dict[str, Any],
        pr_info: PRInfo,
    ) -> str:
        files_summary = []
        for f in pr_diff.get("files", [])[:15]:
            additions = f.get('additions', 0)
            deletions = f.get('deletions', 0)
            files_summary.append(f"- {f.get('filename', '?')} (+{additions}/-{deletions})")

        diff_excerpt = pr_diff.get("diff", "")[:10000]

        return f"""## Pull Request Code Review

### PR Information
- **Title**: {pr_diff.get('title', pr_info.title)}
- **Author**: {pr_diff.get('author', pr_info.author)}
- **Base Branch**: {pr_info.target_branch}
- **Head Branch**: {pr_info.source_branch}
- **PR #**: {pr_info.pr_number}

### Description
{(pr_diff.get('description') or pr_info.description or 'No description')[:1500]}

### Files Changed ({pr_diff.get('changed_files', len(files_summary))} files)
{chr(10).join(files_summary)}

### Diff
```diff
{diff_excerpt}
```

Review this pull request for bugs, security issues, performance problems, and style.
Respond with JSON only."""

    # ══════════════════════════════════════════════════════════
    #  AI API Call (with exponential backoff)
    # ══════════════════════════════════════════════════════════

    async def _call_ai(self, prompt: str, system_prompt: str = "") -> str:
        is_azure = self.config.provider == "azure"

        # Build URL and headers based on provider
        if is_azure:
            url = (
                f"{self.config.active_base_url}"
                f"/chat/completions?api-version={self.config.azure_api_version}"
            )
            headers = {
                "api-key": self.config.active_api_key,
                "Content-Type": "application/json",
            }
        else:
            url = f"{self.config.active_base_url}/chat/completions"
            headers = {
                "Authorization": f"Bearer {self.config.active_api_key}",
                "Content-Type": "application/json",
            }

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload = {
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": self.config.max_tokens,
        }
        # Azure doesn't need model in body (it's in the URL), others do
        if not is_azure:
            payload["model"] = self.config.active_model

        delay = self.base_delay

        for attempt in range(self.max_retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(
                        url,
                        headers=headers,
                        json=payload,
                        timeout=aiohttp.ClientTimeout(total=120),
                    ) as response:
                        if response.status == 200:
                            data = await response.json()
                            content = data["choices"][0]["message"]["content"]
                            # Strip reasoning tags
                            content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL)
                            return content.strip()

                        elif response.status == 429:
                            retry_after = response.headers.get("Retry-After")
                            wait = float(retry_after) if retry_after else delay
                            logger.warning(f"Rate limited (429), waiting {wait:.1f}s (attempt {attempt+1})")
                            await asyncio.sleep(wait)
                            delay = min(delay * 2, 30)
                            continue

                        else:
                            error_text = await response.text()
                            logger.error(f"AI API error {response.status}: {error_text[:300]}")

            except asyncio.TimeoutError:
                logger.warning(f"AI API timeout (attempt {attempt+1})")
            except Exception as e:
                logger.error(f"AI API call failed (attempt {attempt+1}): {e}")

            if attempt < self.max_retries - 1:
                await asyncio.sleep(delay)
                delay = min(delay * 2, 30)

        logger.error("All AI API retries exhausted")
        return "{}"

    # ══════════════════════════════════════════════════════════
    #  Response Parsers
    # ══════════════════════════════════════════════════════════

    def _parse_analysis_response(self, response: str, error: DetectedError) -> RootCauseAnalysis:
        data = _extract_json(response)

        return RootCauseAnalysis(
            error=error,
            root_cause=data.get("root_cause", "Unable to determine root cause"),
            error_category=data.get("error_category", "unknown"),
            severity=data.get("severity", "medium"),
            affected_components=data.get("affected_components", []),
            confidence=float(data.get("confidence", 0.5)),
            additional_context=data.get("additional_context", ""),
            analyzed_at=datetime.utcnow(),
        )

    def _parse_fix_response(self, response: str, error: DetectedError) -> List[FixProposal]:
        data = _extract_json(response)
        raw_proposals = data.get("proposals", [])

        proposals = []
        for p in raw_proposals:
            proposals.append(FixProposal(
                target_file=p.get("target_file", str(error.source_file or "unknown")),
                line_number=int(p.get("line_number", error.line_number or 0)),
                original_code=p.get("original_code", ""),
                suggested_code=p.get("suggested_code", p.get("code_suggestion", "")),
                explanation=p.get("explanation", p.get("description", "No explanation")),
                risk_level=p.get("risk_level", "medium"),
                confidence=float(p.get("confidence", 0.5)),
                side_effects=p.get("side_effects", p.get("potential_side_effects", [])),
            ))

        if not proposals and data:
            # AI might have returned a single proposal not wrapped in array
            if "suggested_code" in data or "original_code" in data:
                proposals.append(FixProposal(
                    target_file=data.get("target_file", str(error.source_file or "unknown")),
                    line_number=int(data.get("line_number", error.line_number or 0)),
                    original_code=data.get("original_code", ""),
                    suggested_code=data.get("suggested_code", ""),
                    explanation=data.get("explanation", ""),
                    risk_level=data.get("risk_level", "medium"),
                    confidence=float(data.get("confidence", 0.5)),
                    side_effects=data.get("side_effects", []),
                ))

        return proposals

    def _parse_review_response(self, response: str, pr_info: PRInfo) -> CodeReviewResult:
        data = _extract_json(response)

        comments = []
        for c in data.get("comments", []):
            raw_line = c.get("line_number", c.get("line", 0))
            comments.append(CodeReviewComment(
                file_path=c.get("file_path", c.get("file", "")),
                line_number=int(raw_line) if raw_line is not None else 0,
                severity=c.get("severity", "info"),
                comment_type=c.get("comment_type", c.get("category", "suggestion")),
                message=c.get("message", c.get("comment", "")),
                suggested_fix=c.get("suggested_fix", c.get("suggestion")),
            ))

        return CodeReviewResult(
            pr_info=pr_info,
            overall_assessment=data.get("overall_assessment", "comment"),
            summary=data.get("summary", "Review completed"),
            comments=comments,
            highlights=data.get("highlights", []),
            reviewed_at=datetime.utcnow(),
        )


# ════════════════════════════════════════════════════════════════
#  Singleton
# ════════════════════════════════════════════════════════════════

_analyzer: Optional[AIAnalyzer] = None


def get_ai_analyzer() -> AIAnalyzer:
    """Get or create the AI analyzer singleton."""
    global _analyzer
    if _analyzer is None:
        _analyzer = AIAnalyzer()
    return _analyzer
