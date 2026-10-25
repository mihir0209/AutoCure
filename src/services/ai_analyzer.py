"""
AI Analyzer Service for the Self-Healing Software System v2.0

Features:
- Root cause analysis with AST context + tool-calling
- Exact fix proposal generation (precise code diffs)
- Chat history: analysis → fix conversation is shared (saves tokens)
- Repository tools: search_code, dir_tree, read_file (AI calls on demand)
- Code review for pull requests
- Robust JSON extraction with fallback parsing
"""

import asyncio
import json
import re
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
import aiohttp

from config import get_config
from services.ast_review_service import get_ast_review_service
from utils.models import (
    DetectedError, ASTContext, RootCauseAnalysis, FixProposal,
    PRInfo, CodeReviewComment, CodeReviewResult, ErrorReplicationSummary,
    AIAnalysisResponse, AIFixResponse, AICodeReviewResponse,
)
from utils.logger import setup_colored_logger
from pydantic import ValidationError


logger = setup_colored_logger("ai_analyzer")


# ════════════════════════════════════════════════════════════════
#  Helpers
# ════════════════════════════════════════════════════════════════

def _extract_json(text: str) -> dict:
    """
    Extract JSON from AI response, handling markdown fences and preamble.
    Returns empty dict on failure (fallback for legacy code).
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


def _parse_with_pydantic(text: str, model_class):
    """
    Parse AI response using Pydantic model for robust validation.
    Falls back to JSON extraction if Pydantic parsing fails.
    
    Returns: (parsed_model_or_dict, success: bool)
    """
    if not text:
        return {}, False
    
    # Extract JSON first
    data = _extract_json(text)
    if not data:
        logger.warning(f"Could not extract JSON from AI response (len={len(text)})")
        return {}, False
    
    # Try Pydantic validation
    try:
        validated = model_class(**data)
        return validated, True
    except ValidationError as e:
        logger.warning(f"Pydantic validation failed for {model_class.__name__}: {e}")
        # Return raw dict as fallback
        return data, False
    except Exception as e:
        logger.error(f"Unexpected error in Pydantic parsing: {e}")
        return data, False


class AIAnalyzer:
    """
    AI-powered analysis service with tool-calling and chat history.

    Key features:
    - Tool calling: AI can search_code, dir_tree, read_file on demand
    - Chat history: analysis → fix share one conversation (saves tokens)
    - Exponential backoff for rate limiting
    """

    def __init__(self, config=None):
        self.config = config or get_config().ai
        self.max_retries = self.config.max_retries
        self.base_delay = self.config.initial_retry_delay
        self.ast_review_service = get_ast_review_service()

    @property
    def is_mock(self) -> bool:
        """Check if AI analyzer should run in deterministic offline/mock mode."""
        if getattr(self.config, "provider", None) == "mock":
            return True
        if os.getenv("AI_PROVIDER", "").lower() == "mock":
            return True
        if os.getenv("MOCK_AI", "").lower() in ("1", "true", "yes"):
            return True
        active_key = getattr(self.config, "active_api_key", "")
        if not active_key or active_key.strip().lower() in (
            "your_groq_api_key_here",
            "your_cerebras_api_key_here",
            "your_api_key_here",
            "changeme",
        ):
            return True
        return False

    def _generate_mock_analysis_json(
        self, error: DetectedError, source_code: Optional[str] = None
    ) -> str:
        err_type = error.error_type or "UnknownError"
        msg = error.message or ""

        category_map = {
            "IndexError": "index_error",
            "KeyError": "key_error",
            "TypeError": "type_error",
            "AttributeError": "attribute_error",
            "ZeroDivisionError": "logic_error",
            "ValueError": "validation_error",
            "ImportError": "import_error",
            "ModuleNotFoundError": "import_error",
            "FileNotFoundError": "other",
            "ConnectionError": "network_error",
            "DatabaseConnectionError": "network_error",
            "SyntaxError": "syntax_error",
        }
        category = category_map.get(err_type, "logic_error" if "Error" in err_type else "other")
        root_cause = (
            f"{err_type}: {msg}. "
            f"AST analysis localized error to {error.source_file or 'unknown'}:{error.line_number or 0}."
        )

        mock_data = {
            "root_cause": root_cause,
            "error_category": category,
            "severity": "high" if "Error" in err_type else "medium",
            "affected_components": [f"{error.source_file or 'app'}:{error.line_number or 1}"],
            "confidence": 0.95,
            "additional_context": "Deterministic mock analysis based on AST trace and error details.",
            "error_pin": None,
        }
        return json.dumps(mock_data)

    def _generate_mock_fix_json(
        self,
        error: DetectedError,
        analysis: RootCauseAnalysis,
        source_code: str = "",
    ) -> str:
        target_file = str(error.source_file or "unknown")
        line_number = int(error.line_number or 1)
        original_code = ""
        suggested_code = ""

        if source_code:
            lines = source_code.splitlines()
            for l in lines:
                if l.strip().startswith(">>>"):
                    clean = re.sub(r'^\s*>>>\s*\d+\s*\|\s*', '', l)
                    if clean:
                        original_code = clean
                        break
            if not original_code and 0 < line_number <= len(lines):
                original_code = lines[line_number - 1].strip()

        if not original_code:
            original_code = "# Execution failure"

        err_type = error.error_type or ""
        msg = error.message or ""

        if "ZeroDivision" in err_type or "division by zero" in msg:
            div_match = re.search(r'/\s*([a-zA-Z_]\w*)', original_code)
            div_var = div_match.group(1) if div_match else "count"
            suggested_code = (
                f"return total / {div_var} if {div_var} != 0 else 0"
                if "return" in original_code else
                f"if {div_var} != 0:\n    {original_code}"
            )
            explanation = "Guard against ZeroDivisionError by checking that divisor is non-zero."
        elif "IndexError" in err_type or "out of range" in msg:
            suggested_code = (
                "return items[index] if 0 <= index < len(items) else None"
                if "return" in original_code else
                f"if 0 <= index < len(items):\n    {original_code}"
            )
            explanation = "Check sequence bounds before indexing to avoid IndexError."
        elif "KeyError" in err_type:
            suggested_code = (
                "return data.get(key, None)"
                if "return" in original_code else
                f"if key in data:\n    {original_code}"
            )
            explanation = "Check key existence or use .get() with fallback."
        elif "TypeError" in err_type:
            suggested_code = f"if val is not None:\n    {original_code}"
            explanation = "Validate types and nullability before evaluation."
        else:
            suggested_code = (
                f"try:\n    {original_code}\nexcept Exception as e:\n    return None"
            )
            explanation = "Defensive exception handling around vulnerable statement."

        mock_fix = {
            "proposals": [
                {
                    "target_file": target_file,
                    "line_number": line_number,
                    "original_code": original_code,
                    "suggested_code": suggested_code,
                    "explanation": explanation,
                    "risk_level": "low",
                    "confidence": 0.95,
                    "side_effects": [],
                }
            ]
        }
        return json.dumps(mock_fix)

    def _generate_mock_review_json(self, pr_info: PRInfo) -> str:
        mock_review = {
            "overall_assessment": "approve",
            "overall_score": 90,
            "summary": "Mock PR review completed successfully: code conforms to standards and passes syntax validation.",
            "comments": [
                {
                    "file_path": "main.py",
                    "line_number": 1,
                    "severity": "info",
                    "comment_type": "best_practice",
                    "message": "Module follows recommended structure.",
                    "suggested_fix": None,
                }
            ],
        }
        return json.dumps(mock_review)

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
        repo_path: str = "",
        conversation: Optional[List[Dict]] = None,
    ) -> RootCauseAnalysis:
        """
        Perform root cause analysis on a detected error.

        Args:
            repo_path: Local repo path — enables tool-calling (search, tree, read).
            conversation: Mutable list that will hold chat history.
                          Pass the same list to generate_fix_proposals() to
                          continue the same conversation (saves tokens).
        """
        conv = conversation if conversation is not None else []

        # Build initial messages
        system = self._get_system_prompt()
        user_msg = self._build_analysis_prompt(error, source_code, ast_context, replication_summary)

        if not conv:
            conv.append({"role": "system", "content": system})
        conv.append({"role": "user", "content": user_msg})

        if self.is_mock:
            logger.info("Using mock AI provider for root cause analysis")
            response_text = self._generate_mock_analysis_json(error, source_code)
            conv.append({"role": "assistant", "content": response_text})
            return self._parse_analysis_response(response_text, error)

        # Call AI with tool support
        response_text = await self._call_ai_with_tools(conv, repo_path=repo_path)

        return self._parse_analysis_response(response_text, error)

    async def generate_fix_proposals(
        self,
        error: DetectedError,
        analysis: RootCauseAnalysis,
        source_code: str,
        ast_context=None,
        user_id: str = "",
        repo_path: str = "",
        conversation: Optional[List[Dict]] = None,
    ) -> List[FixProposal]:
        """
        Generate *exact* fix proposals — concrete code that can be applied.

        If *conversation* contains the chat history from analyze_error(),
        the AI already has all context.  Only a short follow-up message is sent,
        saving ~60 % of tokens compared to rebuilding the full prompt.
        """
        conv = conversation if conversation is not None else []

        if conv:
            # Continue existing conversation — AI already has the context
            followup = self._build_fix_followup(error)
            conv.append({"role": "user", "content": followup})
        else:
            # Standalone call (no prior conversation)
            conv.append({"role": "system", "content": self._get_system_prompt()})
            conv.append({"role": "user", "content": self._build_fix_prompt(
                error, analysis, source_code, ast_context=ast_context,
            )})

        if self.is_mock:
            logger.info("Using mock AI provider for fix proposal generation")
            response_text = self._generate_mock_fix_json(error, analysis, source_code)
            conv.append({"role": "assistant", "content": response_text})
            return self._parse_fix_response(response_text, error)

        response_text = await self._call_ai_with_tools(conv, repo_path=repo_path)
        return self._parse_fix_response(response_text, error)

    async def review_pull_request(
        self,
        pr_diff: Dict[str, Any],
        pr_info: PRInfo,
        user_id: str = "",
        repo_path: str = "",
        base_ref: str = "",
        head_ref: str = "",
    ) -> CodeReviewResult:
        """Perform AI-powered code review on a pull request."""
        ast_review = self.ast_review_service.analyze_review_diff(
            pr_diff,
            repo_path=repo_path,
            base_ref=base_ref,
            head_ref=head_ref,
        )
        if self.is_mock:
            logger.info("Using mock AI provider for PR review")
            response = self._generate_mock_review_json(pr_info)
            return self._parse_review_response(response, pr_info, ast_review=ast_review)

        prompt = self._build_review_prompt(pr_diff, pr_info, ast_review)
        response = await self._call_ai_simple(prompt, system_prompt=self._get_review_system_prompt())
        return self._parse_review_response(response, pr_info, ast_review=ast_review)

    # ══════════════════════════════════════════════════════════
    #  System Prompts (concise — shared for analysis + fix)
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def _get_system_prompt() -> str:
        return (
            "You are an expert software debugging engineer.\n"
            "You have access to 3 repository tools — use them if the provided context is insufficient:\n"
            "  search_code(query, max_results) — grep for text across the repo\n"
            "  dir_tree(directory, depth)       — show directory structure (max 3 levels)\n"
            "  read_file(file_path, start_line, end_line) — read file contents\n\n"
            "PHASE 1 — When asked to ANALYSE an error:\n"
            "  Pinpoint the EXACT root cause (line, variable, function).\n"
            "  Respond ONLY with JSON:\n"
            "  {\"root_cause\":\"...\", \"error_category\":\"<null_reference|type_error|attribute_error|"
            "key_error|index_error|import_error|syntax_error|logic_error|validation_error|"
            "concurrency_error|network_error|permission_error|configuration_error|dependency_error|other>\","
            " \"severity\":\"<critical|high|medium|low>\", \"affected_components\":[\"mod.Class.func\"],"
            " \"confidence\":0.85, \"additional_context\":\"...\",\n"
            "  \"error_pin\":{\"file\":\"path/to/file.py\",\"line\":42,\"reason\":\"brief why this is the real cause\"}}\n"
            "  Include error_pin ONLY when the reported error line does NOT point to the actual root cause\n"
            "  (e.g. segfaults, C-extension crashes, indirect/null dereferences, library internals).\n\n"
            "PHASE 2 — When asked to GENERATE FIX PROPOSALS:\n"
            "  Create exact, copy-paste-ready code fixes.\n"
            "  ONLY fix executable code — NEVER modify comments or docstrings.\n"
            "  Respond ONLY with JSON:\n"
            "  {\"proposals\":[{\"target_file\":\"path\", \"line_number\":42,"
            " \"original_code\":\"exact buggy code\", \"suggested_code\":\"exact fix\","
            " \"explanation\":\"why\", \"risk_level\":\"low|medium|high\","
            " \"confidence\":0.9, \"side_effects\":[]}]}"
        )

    @staticmethod
    def _get_review_system_prompt() -> str:
        return (
            "You are an expert code reviewer. Focus on correctness, security, best practices.\n"
            "Respond ONLY with JSON:\n"
            "{\"overall_assessment\":\"approve|request_changes|comment\","
            " \"overall_score\": 0-100,"
            " \"summary\":\"...\","
            " \"comments\":[{\"file_path\":\"...\", \"line_number\":42,"
            " \"severity\":\"critical|warning|suggestion|info\","
            " \"comment_type\":\"bug|security|performance|style|documentation|best_practice\","
            " \"message\":\"...\", \"suggested_fix\":\"...\"}],"
            " \"highlights\":[\"good thing\"],"
            " \"ast_insights\":\"explain AST old-vs-new usefulness/redundancy and reference impact\"}"
        )

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
            "## Analyse This Error\n",
            f"**Type**: {error.error_type}",
            f"**Message**: {error.message}",
            f"**File**: {error.source_file}:{error.line_number}",
            f"**Language**: {error.language}",
        ]
        if error.function_name:
            parts.append(f"**Function**: {error.function_name}")

        if error.stack_trace:
            parts += ["", "### Stack Trace", "```", error.stack_trace[:3000], "```"]

        if error.api_endpoint:
            parts.append(f"**Endpoint**: {error.http_method} {error.api_endpoint}")

        # AST-traced context (rich function bodies from call chain)
        if ast_context:
            ctx_str = ast_context if isinstance(ast_context, str) else ""
            if not ctx_str and hasattr(ast_context, 'error_node') and ast_context.error_node:
                n = ast_context.error_node
                ctx_str = f"Error Node: {n.node_type} → {n.name} (L{n.start_line}-{n.end_line})"
            if ctx_str:
                parts += ["", "### AST-Traced Context", ctx_str[:6000]]

        if source_code and not ast_context:
            parts += ["", "### Source Code", "```", source_code[:4000], "```"]

        if replication_summary:
            parts += [
                "", "### Replication",
                f"Reproducible: {replication_summary.is_reproducible}"
                f" ({replication_summary.reproduction_rate:.0%})",
            ]

        parts.append("\nAnalyse this error. Use tools if you need more context. JSON only.")
        return "\n".join(parts)

    @staticmethod
    def _build_fix_followup(error: DetectedError) -> str:
        """Short follow-up used when the analysis conversation already has context."""
        return (
            "Now generate exact fix proposals for the error above.\n"
            f"Target file: {error.source_file}:{error.line_number}\n"
            "Use tools to read the exact code around the error line if needed.\n"
            "IMPORTANT: original_code must be the actual code from the file, "
            "not comments. suggested_code must be the corrected replacement.\n"
            "Respond with JSON only."
        )

    def _build_fix_prompt(
        self,
        error: DetectedError,
        analysis: RootCauseAnalysis,
        source_code: str,
        ast_context=None,
    ) -> str:
        """Full fix prompt for standalone calls (no prior conversation)."""
        parts = [
            "## Generate Fix Proposals\n",
            f"**Error**: {error.error_type} — {error.message}",
            f"**File**: {error.source_file}:{error.line_number}",
            f"**Root Cause**: {analysis.root_cause}",
            f"**Category**: {analysis.error_category}",
        ]
        if error.stack_trace:
            parts += ["", "### Stack Trace", "```", error.stack_trace[:2000], "```"]
        if ast_context:
            ctx_str = ast_context if isinstance(ast_context, str) else str(ast_context)
            parts += ["", "### AST Context", ctx_str[:6000]]
        if source_code:
            parts += ["", "### Source Code", "```", source_code[:4000], "```"]
        parts.append(
            "\nGenerate EXACT fix proposals. original_code = actual buggy line(s), "
            "suggested_code = corrected replacement. JSON only."
        )
        return "\n".join(parts)

    def _build_review_prompt(
        self,
        pr_diff: Dict[str, Any],
        pr_info: PRInfo,
        ast_review: Optional[Dict[str, Any]] = None,
    ) -> str:
        files_summary = []
        for f in pr_diff.get("files", [])[:15]:
            additions = f.get('additions', 0)
            deletions = f.get('deletions', 0)
            files_summary.append(f"- {f.get('filename', '?')} (+{additions}/-{deletions})")

        diff_excerpt = pr_diff.get("diff", "")[:10000]
        ast_context = self._format_ast_review_context(ast_review)

        return (
            f"## PR Review: {pr_diff.get('title', pr_info.title)}\n"
            f"Author: {pr_diff.get('author', pr_info.author)}\n"
            f"Base: {pr_info.target_branch} ← {pr_info.source_branch}\n\n"
            f"### Files Changed\n{chr(10).join(files_summary)}\n\n"
            f"{ast_context}\n"
            f"### Diff\n```diff\n{diff_excerpt}\n```\n\n"
            "Review for bugs, security, performance, and AST-level redundancy/usefulness. "
            "If a change appears redundant or unused by references, call it out clearly. JSON only."
        )

    @staticmethod
    def _format_ast_review_context(ast_review: Optional[Dict[str, Any]]) -> str:
        if not ast_review:
            return ""
        parts = ["### AST Comparison Context"]
        summary = ast_review.get("summary", "")
        if summary:
            parts.append(f"- Summary: {summary}")

        for d in (ast_review.get("ast_diffs", []) or [])[:10]:
            parts.append(
                f"- {d.get('file_path', '?')}: "
                f"added={len(d.get('added_symbols', []))}, "
                f"changed={len(d.get('changed_symbols', []))}, "
                f"removed={len(d.get('removed_symbols', []))}"
            )
            if d.get("redundancy_candidates"):
                sample = d["redundancy_candidates"][:3]
                parts.append(
                    "  redundancy: " + "; ".join(
                        f"{r.get('symbol', '?')}~{r.get('matched_symbol', '?')}" for r in sample
                    )
                )

        refs = ast_review.get("reference_traces", []) or []
        if refs:
            parts.append("- Reference traces (top):")
            for r in refs[:8]:
                parts.append(f"  {r.get('symbol', '?')}: {r.get('total_references', 0)} refs")

        flags = ast_review.get("manual_flags", []) or []
        if flags:
            parts.append("- Manual flags:")
            for f in flags[:8]:
                parts.append(
                    f"  {f.get('file_path', '?')}::{f.get('symbol', '?')} -> {f.get('reason', '')}"
                )
        return "\n".join(parts) + "\n\n"

    # ══════════════════════════════════════════════════════════
    #  AI API — tool-calling loop (with chat history)
    # ══════════════════════════════════════════════════════════

    async def _call_ai_with_tools(
        self,
        messages: List[Dict],
        repo_path: str = "",
        max_rounds: int = 5,
    ) -> str:
        """
        Call the AI with tool-calling support.

        The AI may request tool calls (search_code, dir_tree, read_file).
        Each tool result is appended to *messages* (the chat history) and
        another round is sent — up to *max_rounds* iterations.

        Returns the final text content from the AI.
        """
        from services.repo_tools import get_repo_index, execute_tool, TOOL_DEFINITIONS

        repo_index = get_repo_index(repo_path) if repo_path else None
        tools = TOOL_DEFINITIONS if repo_index else None

        for round_num in range(max_rounds + 1):
            response_msg = await self._raw_api_call(messages, tools=tools)

            tool_calls = response_msg.get("tool_calls") or []
            content = response_msg.get("content") or ""

            if not tool_calls or not repo_index or round_num >= max_rounds:
                # Final answer — append and return
                if content:
                    content = re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()
                messages.append({"role": "assistant", "content": content})
                return content

            # Append the assistant's tool-calling message (preserves tool_calls field)
            messages.append(response_msg)

            # Execute each requested tool
            for tc in tool_calls:
                func_name = tc["function"]["name"]
                try:
                    func_args = json.loads(tc["function"]["arguments"])
                except (json.JSONDecodeError, KeyError):
                    func_args = {}

                result = execute_tool(repo_index, func_name, func_args)
                # Cap tool output to control token usage
                result = result[:4000]

                logger.info(
                    f"Tool [{round_num+1}] {func_name}"
                    f"({', '.join(f'{k}={v!r}' for k, v in func_args.items())}) "
                    f"→ {len(result)} chars"
                )

                messages.append({
                    "role": "tool",
                    "tool_call_id": tc["id"],
                    "content": result,
                })

        return "{}"

    # ──────────────────────────────────────────────────────────
    #  Raw API call (single request, supports tools)
    # ──────────────────────────────────────────────────────────

    async def _raw_api_call(
        self,
        messages: List[Dict],
        tools: Optional[List[Dict]] = None,
    ) -> Dict:
        """Make one API call and return the response message dict."""
        if self.is_mock:
            # Fallback mock for direct raw calls
            last_msg = messages[-1].get("content", "") if messages else ""
            if "FIX" in last_msg.upper():
                content = json.dumps({"proposals": []})
            elif "REVIEW" in last_msg.upper():
                content = json.dumps({
                    "overall_assessment": "approve",
                    "overall_score": 90,
                    "summary": "Mock review passed",
                    "comments": [],
                })
            else:
                content = json.dumps({
                    "root_cause": "Mock root cause analysis",
                    "error_category": "logic_error",
                    "severity": "medium",
                    "affected_components": ["system"],
                    "confidence": 0.9,
                    "additional_context": "Mock fallback",
                    "error_pin": None,
                })
            return {"content": content}

        is_azure = self.config.provider == "azure"

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

        payload: Dict[str, Any] = {
            "messages": messages,
            "temperature": 0.2,
            "max_tokens": self.config.max_tokens,
        }
        if not is_azure:
            payload["model"] = self.config.active_model
        if tools:
            payload["tools"] = tools
            payload["tool_choice"] = "auto"

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
                            return data["choices"][0]["message"]

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
        return {"content": "{}"}

    # ──────────────────────────────────────────────────────────
    #  Legacy simple call (for code review — no tools needed)
    # ──────────────────────────────────────────────────────────

    async def _call_ai_simple(self, prompt: str, system_prompt: str = "") -> str:
        """Single request-response call without tools (used for PR reviews)."""
        messages: List[Dict] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        msg = await self._raw_api_call(messages)
        content = msg.get("content", "")
        return re.sub(r'<think>.*?</think>', '', content, flags=re.DOTALL).strip()

    # ══════════════════════════════════════════════════════════
    #  Response Parsers
    # ══════════════════════════════════════════════════════════

    def _parse_analysis_response(self, response: str, error: DetectedError) -> RootCauseAnalysis:
        """Parse AI analysis response into RootCauseAnalysis object with Pydantic validation."""
        # Try Pydantic validation first
        parsed_data, validation_success = _parse_with_pydantic(response, AIAnalysisResponse)
        
        if validation_success and isinstance(parsed_data, AIAnalysisResponse):
            # Use validated Pydantic model
            return RootCauseAnalysis(
                error=error,
                root_cause=parsed_data.root_cause,
                error_category=parsed_data.error_category,
                severity=parsed_data.severity,
                confidence=parsed_data.confidence,
                additional_context=parsed_data.additional_context,
                affected_components=parsed_data.affected_components or [],
                error_pin_file=parsed_data.error_pin.file if parsed_data.error_pin else "",
                error_pin_line=parsed_data.error_pin.line if parsed_data.error_pin else 0,
                error_pin_reason=parsed_data.error_pin.reason if parsed_data.error_pin else "",
            )
        
        # Fallback to manual dict parsing
        data = parsed_data if isinstance(parsed_data, dict) else {}
        logger.warning(f"Using fallback parsing for analysis response (validation failed)")
        
        return RootCauseAnalysis(
            error=error,
            root_cause=data.get("root_cause", "Unable to determine root cause"),
            error_category=data.get("error_category", "unknown"),
            severity=data.get("severity", "medium"),
            confidence=float(data.get("confidence", 0.5)),
            additional_context=data.get("additional_context", ""),
            affected_components=data.get("affected_components", []),
            error_pin_file=data.get("error_pin_file", ""),
            error_pin_line=int(data.get("error_pin_line", 0)) if data.get("error_pin_line") else 0,
            error_pin_reason=data.get("error_pin_reason", ""),
        )

    def _parse_fix_response(self, response: str, error: DetectedError) -> List[FixProposal]:
        """Parse AI fix response into FixProposal objects with Pydantic validation."""
        # Try Pydantic validation first
        parsed_data, validation_success = _parse_with_pydantic(response, AIFixResponse)
        
        if validation_success and isinstance(parsed_data, AIFixResponse):
            # Use validated Pydantic model
            proposals = []
            for p in parsed_data.proposals:
                proposals.append(FixProposal(
                    target_file=p.target_file,
                    line_number=p.line_number,
                    original_code=p.original_code,
                    suggested_code=p.suggested_code,
                    explanation=p.explanation,
                    risk_level=p.risk_level,
                    confidence=p.confidence,
                    side_effects=p.side_effects or [],
                ))
            return proposals
        
        # Fallback to manual dict parsing
        data = parsed_data if isinstance(parsed_data, dict) else {}
        logger.warning(f"Using fallback parsing for fix response (validation failed)")
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

    def _parse_review_response(
        self,
        response: str,
        pr_info: PRInfo,
        ast_review: Optional[Dict[str, Any]] = None,
    ) -> CodeReviewResult:
        """Parse AI code review response into CodeReviewResult with Pydantic validation."""
        # Try Pydantic validation first
        parsed_data, validation_success = _parse_with_pydantic(response, AICodeReviewResponse)
        
        if validation_success and isinstance(parsed_data, AICodeReviewResponse):
            # Use validated Pydantic model
            comments = []
            for c in parsed_data.comments:
                comments.append(CodeReviewComment(
                    file_path=c.file_path,
                    line_number=c.line_number,
                    severity=c.severity,
                    comment_type=c.comment_type,
                    message=c.message,
                    suggested_fix=c.suggested_fix,
                ))
            
            return CodeReviewResult(
                pr_info=pr_info,
                overall_score=parsed_data.overall_score,
                overall_assessment=parsed_data.overall_assessment,
                summary=parsed_data.summary,
                comments=comments,
                highlights=parsed_data.highlights or [],
                approved=parsed_data.overall_assessment == "approve",
                ast_insights=parsed_data.ast_insights or (ast_review or {}).get("summary", ""),
                ast_diffs=(ast_review or {}).get("ast_diffs", []),
                reference_traces=(ast_review or {}).get("reference_traces", []),
                manual_flags=(ast_review or {}).get("manual_flags", []),
                reviewed_at=datetime.utcnow(),
            )
        
        # Fallback to manual dict parsing
        data = parsed_data if isinstance(parsed_data, dict) else {}
        logger.warning(f"Using fallback parsing for review response (validation failed)")

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
            overall_score=float(data.get("overall_score", 0.0)),
            overall_assessment=data.get("overall_assessment", "comment"),
            summary=data.get("summary", "Review completed"),
            comments=comments,
            highlights=data.get("highlights", []),
            approved=data.get("overall_assessment", "comment") == "approve",
            ast_insights=data.get("ast_insights", (ast_review or {}).get("summary", "")),
            ast_diffs=(ast_review or {}).get("ast_diffs", []),
            reference_traces=(ast_review or {}).get("reference_traces", []),
            manual_flags=(ast_review or {}).get("manual_flags", []),
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
