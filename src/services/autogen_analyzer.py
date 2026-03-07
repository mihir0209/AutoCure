"""
AutoGen-based AI Analyzer for the Self-Healing Software System v2.0

Uses Microsoft AutoGen framework with multi-agent orchestration:
- Error Analyzer Agent: Diagnoses root cause using tools (file reading, AST parsing, codebase search)
- Fix Proposer Agent: Generates exact copy-paste-ready code fixes
- Code Reviewer Agent: Reviews PR diffs for bugs, security, and best practices

Each agent has access to tool functions for investigating the codebase.
Uses Cerebras/Groq via OpenAI-compatible API through OpenAIChatCompletionClient.
"""

import asyncio
import json
import os
import re
from typing import Optional, List, Dict, Any
from datetime import datetime
from pathlib import Path

from config import get_config
from utils.models import (
    DetectedError, RootCauseAnalysis, FixProposal, EdgeTestCase,
    PRInfo, CodeReviewComment, CodeReviewResult, ErrorReplicationSummary
)
from utils.logger import setup_colored_logger

logger = setup_colored_logger("autogen_analyzer")

# AutoGen imports
from autogen_agentchat.agents import AssistantAgent
from autogen_agentchat.conditions import TextMentionTermination, MaxMessageTermination
from autogen_agentchat.teams import RoundRobinGroupChat
from autogen_ext.models.openai import OpenAIChatCompletionClient


# ════════════════════════════════════════════════════════════════
#  JSON Extraction Helper
# ════════════════════════════════════════════════════════════════

def _extract_json(text: str) -> dict:
    """Robustly extract the first JSON object from an AI response."""
    if not text:
        return {}
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL).strip()
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'```\s*$', '', text, flags=re.MULTILINE)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
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
                candidate = re.sub(r',\s*([}\]])', r'\1', candidate)
                try:
                    return json.loads(candidate)
                except json.JSONDecodeError:
                    pass
    return {}


# ════════════════════════════════════════════════════════════════
#  Tool Functions (available to AutoGen agents)
# ════════════════════════════════════════════════════════════════

# These are module-level references set by the AutoGenAnalyzer at runtime
_repos_base: Path = Path("repos")
_current_user_repo: str = ""


async def read_source_file(file_path: str, start_line: int = 1, end_line: int = 100) -> str:
    """Read lines from a repo file. Returns numbered source code."""
    try:
        repo_path = _repos_base / _current_user_repo
        full_path = repo_path / file_path
        if not full_path.exists():
            # Try searching for the file
            for p in repo_path.rglob(Path(file_path).name):
                full_path = p
                break
            else:
                return f"ERROR: File '{file_path}' not found in repository"
        
        lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
        start = max(0, start_line - 1)
        end = min(len(lines), end_line)
        numbered = [f"{i+1:4d} | {lines[i]}" for i in range(start, end)]
        return f"File: {file_path} (lines {start_line}-{end}, total {len(lines)} lines)\n" + "\n".join(numbered)
    except Exception as e:
        return f"ERROR reading file: {e}"


async def list_repo_files(directory: str = ".") -> str:
    """List files and subdirectories in the given repo directory."""
    try:
        repo_path = _repos_base / _current_user_repo / directory
        if not repo_path.exists():
            return f"ERROR: Directory '{directory}' not found"
        
        entries = []
        for item in sorted(repo_path.iterdir()):
            if item.name.startswith('.') or item.name in ('__pycache__', 'node_modules', '.git', 'venv', '.venv'):
                continue
            prefix = "DIR " if item.is_dir() else "FILE"
            entries.append(f"  {prefix}  {item.name}")
        
        return f"Directory: {directory}\n" + "\n".join(entries) if entries else f"Directory '{directory}' is empty"
    except Exception as e:
        return f"ERROR listing directory: {e}"


async def search_codebase(query: str, file_extension: str = "") -> str:
    """Search for text across repo files. Returns matching lines with paths."""
    try:
        repo_path = _repos_base / _current_user_repo
        if not repo_path.exists():
            return "ERROR: Repository not found"
        
        pattern = re.compile(re.escape(query), re.IGNORECASE)
        results = []
        skip_dirs = {'.git', '__pycache__', 'node_modules', 'venv', '.venv', 'dist', 'build'}
        
        for filepath in repo_path.rglob("*"):
            if filepath.is_dir():
                continue
            if any(sd in filepath.parts for sd in skip_dirs):
                continue
            if file_extension and not filepath.name.endswith(file_extension):
                continue
            try:
                content = filepath.read_text(encoding="utf-8", errors="replace")
                for line_num, line in enumerate(content.splitlines(), 1):
                    if pattern.search(line):
                        rel = filepath.relative_to(repo_path)
                        results.append(f"  {rel}:{line_num}: {line.strip()[:120]}")
                        if len(results) >= 30:
                            return f"Search results for '{query}':\n" + "\n".join(results) + "\n  ... (truncated at 30 results)"
            except (UnicodeDecodeError, PermissionError):
                continue
        
        if not results:
            return f"No results found for '{query}'"
        return f"Search results for '{query}' ({len(results)} matches):\n" + "\n".join(results)
    except Exception as e:
        return f"ERROR searching: {e}"


async def get_error_context(error_file: str, error_line: int) -> str:
    """Get 30 lines of code context around an error location plus imports."""
    try:
        repo_path = _repos_base / _current_user_repo
        full_path = repo_path / error_file
        if not full_path.exists():
            for p in repo_path.rglob(Path(error_file).name):
                full_path = p
                break
            else:
                return f"ERROR: File '{error_file}' not found"
        
        lines = full_path.read_text(encoding="utf-8", errors="replace").splitlines()
        
        # Show 30 lines before and after the error
        start = max(0, error_line - 31)
        end = min(len(lines), error_line + 30)
        
        numbered = []
        for i in range(start, end):
            marker = " >>>" if i + 1 == error_line else "    "
            numbered.append(f"{marker} {i+1:4d} | {lines[i]}")
        
        # Also get imports (first 30 lines)
        imports = []
        for i in range(min(30, len(lines))):
            line = lines[i].strip()
            if line.startswith(('import ', 'from ', 'require(', '#include', 'using ')):
                imports.append(f"      {i+1:4d} | {lines[i]}")
        
        result = f"Error context for {error_file}:{error_line}\n\n"
        if imports:
            result += "=== Imports ===\n" + "\n".join(imports) + "\n\n"
        result += "=== Code around error (>>> marks error line) ===\n" + "\n".join(numbered)
        
        return result
    except Exception as e:
        return f"ERROR getting context: {e}"


async def parse_ast_structure(file_path: str) -> str:
    """Get high-level AST structure (classes, functions, imports) of a file."""
    try:
        from services.ast_service import ASTService
        ast_service = ASTService()
        
        repo_path = _repos_base / _current_user_repo
        full_path = repo_path / file_path
        if not full_path.exists():
            for p in repo_path.rglob(Path(file_path).name):
                full_path = p
                break
            else:
                return f"ERROR: File '{file_path}' not found"
        
        root = ast_service.parse_file(str(full_path))
        if not root:
            return f"ERROR: Could not parse '{file_path}'"
        
        # Build structural summary
        summary = [f"AST Structure for {file_path}:"]
        
        def walk(node, depth=0):
            indent = "  " * depth
            node_type = node.type if hasattr(node, 'type') else str(type(node).__name__)
            
            # Only show structural nodes
            interesting = {'module', 'class_definition', 'function_definition', 
                          'decorated_definition', 'import_statement', 'import_from_statement',
                          'class_declaration', 'function_declaration', 'method_definition',
                          'assignment', 'if_statement', 'for_statement', 'try_statement',
                          'expression_statement', 'return_statement'}
            
            if node_type in interesting or depth < 2:
                name = ""
                if hasattr(node, 'child_by_field_name'):
                    name_node = node.child_by_field_name('name')
                    if name_node:
                        name = f" '{name_node.text.decode() if isinstance(name_node.text, bytes) else name_node.text}'"
                
                start_line = node.start_point[0] + 1 if hasattr(node, 'start_point') else 0
                end_line = node.end_point[0] + 1 if hasattr(node, 'end_point') else 0
                
                summary.append(f"{indent}{node_type}{name} (L{start_line}-{end_line})")
            
            if hasattr(node, 'children'):
                for child in node.children:
                    if depth < 5:
                        walk(child, depth + 1)
        
        walk(root)
        return "\n".join(summary[:100])  # Limit output
    except Exception as e:
        return f"ERROR parsing AST: {e}"


async def find_symbol_usages(symbol_name: str, file_extension: str = "") -> str:
    """Find all definitions and usages of a symbol (function, class, variable) across the codebase using AST-aware search.
    Returns where the symbol is defined, imported, and called/referenced."""
    try:
        repo_path = _repos_base / _current_user_repo
        if not repo_path.exists():
            return "ERROR: Repository not found"

        skip_dirs = {'.git', '__pycache__', 'node_modules', 'venv', '.venv', 'dist', 'build'}
        pattern = re.compile(r'\b' + re.escape(symbol_name) + r'\b')

        definitions = []
        imports = []
        usages = []

        for filepath in repo_path.rglob("*"):
            if filepath.is_dir():
                continue
            if any(sd in filepath.parts for sd in skip_dirs):
                continue
            if file_extension and not filepath.name.endswith(file_extension):
                continue
            if filepath.suffix not in ('.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rs', '.rb', '.php', '.c', '.cpp', '.cs'):
                continue
            try:
                lines = filepath.read_text(encoding="utf-8", errors="replace").splitlines()
                rel = str(filepath.relative_to(repo_path))
                for i, line in enumerate(lines):
                    stripped = line.strip()
                    if not pattern.search(line):
                        continue
                    loc = f"  {rel}:{i+1}: {stripped[:120]}"
                    # Classify: definition, import, or usage
                    if any(stripped.startswith(kw) for kw in ('def ', 'class ', 'function ', 'const ', 'let ', 'var ', 'async def ', 'async function ')):
                        definitions.append(loc)
                    elif any(stripped.startswith(kw) for kw in ('import ', 'from ', 'require(', '#include', 'using ')):
                        imports.append(loc)
                    else:
                        usages.append(loc)
            except (UnicodeDecodeError, PermissionError):
                continue

        parts = [f"Symbol analysis for '{symbol_name}':"]
        if definitions:
            parts.append(f"\n=== Definitions ({len(definitions)}) ===")
            parts.extend(definitions[:10])
        if imports:
            parts.append(f"\n=== Imports ({len(imports)}) ===")
            parts.extend(imports[:10])
        if usages:
            parts.append(f"\n=== Usages ({len(usages)}) ===")
            parts.extend(usages[:20])
        if not definitions and not imports and not usages:
            parts.append("  No references found")
        return "\n".join(parts)
    except Exception as e:
        return f"ERROR finding usages: {e}"


# ════════════════════════════════════════════════════════════════
#  AutoGen Analyzer Class
# ════════════════════════════════════════════════════════════════

class AutoGenAnalyzer:
    """
    AI-powered analysis service using Microsoft AutoGen framework.
    
    Uses multiple specialized agents with tool access:
    - Error Analyzer: Investigates errors using file reading, AST parsing, search
    - Fix Proposer: Generates exact code fixes based on analysis
    - Code Reviewer: Reviews pull request diffs
    
    All agents use Cerebras/Groq via OpenAI-compatible API.
    """

    def __init__(self, config=None):
        self.config = config or get_config().ai
        self._model_client = None
        
    def _get_model_client(self) -> OpenAIChatCompletionClient:
        """Create or return the OpenAI-compatible model client for Cerebras/Groq."""
        if self._model_client is None:
            self._model_client = OpenAIChatCompletionClient(
                model=self.config.active_model,
                base_url=self.config.active_base_url,
                api_key=self.config.active_api_key,
                model_info={
                    "vision": False,
                    "function_calling": True,
                    "json_output": True,
                    "family": "unknown",
                    "structured_output": True,
                },
            )
        return self._model_client

    def _setup_repo_context(self, user_id: str = ""):
        """Set the repo context for tool functions.
        
        The actual repo lives at repos/{user_id}/{owner}_{repo_name}/.
        We need to find that subdirectory.
        """
        global _repos_base, _current_user_repo
        cfg = get_config()
        _repos_base = cfg.github.repos_base_path
        
        if user_id:
            # The repo is in a subdirectory: repos/{user_id}/{owner}_{repo_name}/
            user_dir = _repos_base / user_id
            if user_dir.exists():
                subdirs = [d for d in user_dir.iterdir() if d.is_dir() and d.name != '.git']
                if subdirs:
                    # Use the first repo subdirectory (usually only one)
                    _current_user_repo = f"{user_id}/{subdirs[0].name}"
                    return
        _current_user_repo = user_id

    # ──────────────────────────────────────────────────────────
    #  Public API (matches AIAnalyzer interface)
    # ──────────────────────────────────────────────────────────

    async def analyze_error(
        self,
        error: DetectedError,
        source_code: Optional[str] = None,
        ast_context=None,
        replication_summary: Optional[ErrorReplicationSummary] = None,
        user_id: str = "",
    ) -> RootCauseAnalysis:
        """Perform root cause analysis using AutoGen agent with tools."""
        self._setup_repo_context(user_id)
        
        # Build the task description for the agent
        task = self._build_analysis_task(error, source_code, ast_context, replication_summary)
        
        try:
            model_client = self._get_model_client()
            
            # Create analyzer agent with tools
            tools = [read_source_file, list_repo_files, search_codebase, 
                     get_error_context, parse_ast_structure]
            
            analyzer_agent = AssistantAgent(
                name="error_analyzer",
                model_client=model_client,
                tools=tools,
                system_message=self._get_analysis_system_prompt(),
                reflect_on_tool_use=True,
            )
            
            # Create a termination condition
            termination = MaxMessageTermination(max_messages=15)
            
            # Use RoundRobinGroupChat with single agent (allows tool use loop)
            team = RoundRobinGroupChat(
                participants=[analyzer_agent],
                termination_condition=termination,
            )
            
            # Run the analysis
            logger.info(f"AutoGen: Starting error analysis for {error.error_type}")
            result = await team.run(task=task)
            
            # Extract the final response
            final_response = ""
            if result and result.messages:
                # Get the last text message from the agent
                for msg in reversed(result.messages):
                    content = getattr(msg, 'content', '')
                    if isinstance(content, str) and content.strip() and '{' in content:
                        final_response = content
                        break
                if not final_response:
                    # Fall back to last message
                    for msg in reversed(result.messages):
                        content = getattr(msg, 'content', '')
                        if isinstance(content, str) and content.strip():
                            final_response = content
                            break
            
            logger.info(f"AutoGen: Analysis complete, parsing response")
            return self._parse_analysis_response(final_response, error)
            
        except Exception as e:
            logger.error(f"AutoGen analysis failed: {e}")
            import traceback
            traceback.print_exc()
            # Return a basic analysis on failure
            return RootCauseAnalysis(
                error=error,
                root_cause=f"Analysis failed: {str(e)}",
                error_category="unknown",
                severity="medium",
                affected_components=[],
                confidence=0.1,
                additional_context="AutoGen analysis encountered an error",
                analyzed_at=datetime.utcnow(),
            )

    async def generate_fix_proposals(
        self,
        error: DetectedError,
        analysis: RootCauseAnalysis,
        source_code: str,
        user_id: str = "",
    ) -> List[FixProposal]:
        """Generate exact fix proposals using AutoGen agent with tools."""
        self._setup_repo_context(user_id)
        
        task = self._build_fix_task(error, analysis, source_code)
        
        try:
            model_client = self._get_model_client()
            
            tools = [read_source_file, search_codebase, get_error_context]
            
            fix_agent = AssistantAgent(
                name="fix_proposer",
                model_client=model_client,
                tools=tools,
                system_message=self._get_fix_system_prompt(),
                reflect_on_tool_use=True,
            )
            
            termination = MaxMessageTermination(max_messages=10)
            team = RoundRobinGroupChat(
                participants=[fix_agent],
                termination_condition=termination,
            )
            
            logger.info("AutoGen: Generating fix proposals")
            result = await team.run(task=task)
            
            final_response = ""
            if result and result.messages:
                for msg in reversed(result.messages):
                    content = getattr(msg, 'content', '')
                    if isinstance(content, str) and content.strip() and '{' in content:
                        final_response = content
                        break
            
            return self._parse_fix_response(final_response, error)
            
        except Exception as e:
            logger.error(f"AutoGen fix generation failed: {e}")
            return []

    async def review_pull_request(
        self,
        pr_diff: Dict[str, Any],
        pr_info: PRInfo,
        user_id: str = "",
    ) -> CodeReviewResult:
        """Perform AI-powered code review with AST analysis using AutoGen agent."""
        self._setup_repo_context(user_id)
        
        task = self._build_review_task(pr_diff, pr_info)
        
        try:
            model_client = self._get_model_client()
            
            tools = [read_source_file, search_codebase, parse_ast_structure, find_symbol_usages]
            
            reviewer_agent = AssistantAgent(
                name="code_reviewer",
                model_client=model_client,
                tools=tools,
                system_message=self._get_review_system_prompt(),
                reflect_on_tool_use=True,
            )
            
            termination = MaxMessageTermination(max_messages=14)
            team = RoundRobinGroupChat(
                participants=[reviewer_agent],
                termination_condition=termination,
            )
            
            logger.info(f"AutoGen: Reviewing PR #{pr_info.pr_number}")
            result = await team.run(task=task)
            
            final_response = ""
            if result and result.messages:
                for msg in reversed(result.messages):
                    content = getattr(msg, 'content', '')
                    if isinstance(content, str) and content.strip() and '{' in content:
                        final_response = content
                        break
            
            return self._parse_review_response(final_response, pr_info)
            
        except Exception as e:
            logger.error(f"AutoGen PR review failed: {e}")
            return CodeReviewResult(
                pr_info=pr_info,
                overall_assessment="comment",
                summary=f"Review failed: {str(e)}",
                comments=[],
                highlights=[],
                reviewed_at=datetime.utcnow(),
            )

    # ══════════════════════════════════════════════════════════
    #  System Prompts
    # ══════════════════════════════════════════════════════════

    @staticmethod
    def _get_analysis_system_prompt() -> str:
        return """You are a debugging expert. Use the provided tools to investigate errors in the codebase.

WORKFLOW: Use get_error_context and read_source_file to examine code, search_codebase to find patterns, then respond with JSON:
{"root_cause": "...", "error_category": "null_reference|type_error|attribute_error|key_error|index_error|import_error|logic_error|other", "severity": "critical|high|medium|low", "affected_components": [], "confidence": 0.85, "additional_context": "..."}

Your final message MUST contain this JSON."""

    @staticmethod
    def _get_fix_system_prompt() -> str:
        return """You are a software engineer. Use tools to read source files, then propose exact code fixes.
Also generate edge test cases that the ORIGINAL buggy code would FAIL on, but your proposed fix would PASS.

Respond with JSON:
{"proposals": [{"target_file": "path", "line_number": 42, "original_code": "exact original", "suggested_code": "exact fix", "explanation": "why", "risk_level": "low|medium|high", "confidence": 0.9, "side_effects": [], "test_cases": [{"test_name": "test_name", "description": "what this tests", "test_code": "runnable test code", "expected_behavior": "what should happen with the fix"}]}]}"""

    @staticmethod
    def _get_review_system_prompt() -> str:
        return """You are a thorough code reviewer with AST analysis capabilities.

WORKFLOW:
1. Read changed files using read_source_file
2. Use parse_ast_structure to understand the structure of modified files
3. Use find_symbol_usages to trace how modified functions/classes are used across the codebase
4. Use search_codebase to find related patterns and potential impacts
5. Identify bugs, security issues, performance problems, and style concerns

Focus on: origin of symbols (where defined/imported), how they're used (call sites), and whether changes break existing consumers.

Respond with JSON:
{"overall_assessment": "approve|request_changes|comment", "summary": "Brief summary", "comments": [{"file_path": "path", "line_number": 42, "severity": "critical|warning|suggestion|info", "comment_type": "bug|security|performance|style|impact", "message": "...", "suggested_fix": "optional code", "code_snippet": "relevant original code"}], "highlights": [], "ast_insights": "summary of AST-based findings about symbol usage and impact"}"""

    # ══════════════════════════════════════════════════════════
    #  Task Builders
    # ══════════════════════════════════════════════════════════

    def _build_analysis_task(
        self,
        error: DetectedError,
        source_code: Optional[str],
        ast_context,
        replication_summary: Optional[ErrorReplicationSummary],
    ) -> str:
        parts = [
            "## Error Analysis\n",
            f"**Type**: {error.error_type}",
            f"**Message**: {error.message}",
            f"**File**: {error.source_file}:{error.line_number}",
        ]

        if error.stack_trace:
            parts += ["", "### Stack Trace", "```", error.stack_trace[:1500], "```"]

        if source_code:
            parts += ["", "### Source", "```", source_code[:1500], "```"]

        if ast_context:
            ctx = ast_context if isinstance(ast_context, str) else str(ast_context)
            parts.append(f"\n### AST Context\n{ctx[:2000]}")

        parts.append("\nUse tools to investigate, then respond with JSON analysis.")
        return "\n".join(parts)

    def _build_fix_task(
        self,
        error: DetectedError,
        analysis: RootCauseAnalysis,
        source_code: str,
    ) -> str:
        return f"""## Fix Proposal

### Error: {error.error_type} in {error.source_file}:{error.line_number}
{error.message}

### Root Cause
{analysis.root_cause}

### Source
```
{source_code[:2000]}
```

Use tools to read the actual source, then propose exact JSON fix proposals.

**IMPORTANT**: For each fix proposal, also generate 2-3 edge test cases that:
1. The ORIGINAL buggy code would FAIL on
2. Your proposed fix would PASS

Include test_cases in each proposal with runnable test code."""

    def _build_review_task(
        self,
        pr_diff: Dict[str, Any],
        pr_info: PRInfo,
    ) -> str:
        files_summary = []
        changed_symbols = []
        for f in pr_diff.get("files", [])[:15]:
            additions = f.get('additions', 0)
            deletions = f.get('deletions', 0)
            filename = f.get('filename', '?')
            files_summary.append(f"- {filename} (+{additions}/-{deletions})")
            # Extract function/class names from the patch headers for AST tracing
            patch = f.get('patch', '')
            for line in patch.split('\n'):
                if line.startswith('@@') and '@@' in line[2:]:
                    # Extract function context from hunk header (e.g. @@ -10,5 +10,7 @@ def my_func)
                    header_ctx = line.split('@@')[-1].strip()
                    if header_ctx:
                        # Extract symbol name from context like "def foo" or "class Bar"
                        for kw in ('def ', 'class ', 'function ', 'async def ', 'async function '):
                            if kw in header_ctx:
                                sym = header_ctx.split(kw)[-1].split('(')[0].split(':')[0].strip()
                                if sym and sym not in changed_symbols:
                                    changed_symbols.append(sym)

        diff_excerpt = pr_diff.get("diff", "")[:8000]

        ast_instructions = ""
        if changed_symbols:
            ast_instructions = f"""
### Modified Symbols (trace with find_symbol_usages)
{', '.join(changed_symbols[:10])}

**IMPORTANT**: Use `find_symbol_usages` for each modified symbol above to understand where it's defined, imported, and called. Check if the changes break any existing callers. Use `parse_ast_structure` on modified files to understand the full code structure."""

        return f"""## Pull Request Code Review

Review this pull request for bugs, security issues, performance, and style.
Use AST analysis tools to understand symbol origins and downstream impacts.

### PR Information
- **Title**: {pr_diff.get('title', pr_info.title)}
- **Author**: {pr_diff.get('author', pr_info.author)}
- **Base Branch**: {pr_info.target_branch}
- **Head Branch**: {pr_info.source_branch}

### Description
{(pr_diff.get('description') or pr_info.description or 'No description')[:1500]}

### Files Changed ({pr_diff.get('changed_files', len(files_summary))} files)
{chr(10).join(files_summary)}
{ast_instructions}

### Diff
```diff
{diff_excerpt}
```

**INSTRUCTIONS**: 
1. Use read_source_file to read the full context of changed files
2. Use parse_ast_structure on changed files to understand code structure
3. Use find_symbol_usages to trace how modified symbols are used across the codebase
4. Check for breaking changes in downstream consumers
5. Provide your review as JSON with code_snippet fields showing relevant original code"""

    # ══════════════════════════════════════════════════════════
    #  Response Parsers (same as AIAnalyzer)
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
            # Parse test cases
            test_cases = []
            for tc in p.get("test_cases", []):
                test_cases.append(EdgeTestCase(
                    test_name=tc.get("test_name", ""),
                    description=tc.get("description", ""),
                    test_code=tc.get("test_code", ""),
                    expected_behavior=tc.get("expected_behavior", ""),
                    original_would_fail=tc.get("original_would_fail", True),
                    fix_would_pass=tc.get("fix_would_pass", True),
                ))
            proposals.append(FixProposal(
                target_file=p.get("target_file", str(error.source_file or "unknown")),
                line_number=int(p.get("line_number", error.line_number or 0)),
                original_code=p.get("original_code", ""),
                suggested_code=p.get("suggested_code", p.get("code_suggestion", "")),
                explanation=p.get("explanation", p.get("description", "No explanation")),
                risk_level=p.get("risk_level", "medium"),
                confidence=float(p.get("confidence", 0.5)),
                side_effects=p.get("side_effects", p.get("potential_side_effects", [])),
                test_cases=test_cases,
            ))
        if not proposals and data:
            if "suggested_code" in data or "original_code" in data:
                test_cases = []
                for tc in data.get("test_cases", []):
                    test_cases.append(EdgeTestCase(
                        test_name=tc.get("test_name", ""),
                        description=tc.get("description", ""),
                        test_code=tc.get("test_code", ""),
                        expected_behavior=tc.get("expected_behavior", ""),
                    ))
                proposals.append(FixProposal(
                    target_file=data.get("target_file", str(error.source_file or "unknown")),
                    line_number=int(data.get("line_number", error.line_number or 0)),
                    original_code=data.get("original_code", ""),
                    suggested_code=data.get("suggested_code", ""),
                    explanation=data.get("explanation", ""),
                    risk_level=data.get("risk_level", "medium"),
                    confidence=float(data.get("confidence", 0.5)),
                    side_effects=data.get("side_effects", []),
                    test_cases=test_cases,
                ))
        return proposals

    def _parse_review_response(self, response: str, pr_info: PRInfo) -> CodeReviewResult:
        data = _extract_json(response)
        comments = []
        for c in data.get("comments", []):
            comments.append(CodeReviewComment(
                file_path=c.get("file_path", c.get("file", "")),
                line_number=c.get("line_number", c.get("line", 0)),
                severity=c.get("severity", "info"),
                comment_type=c.get("comment_type", c.get("category", "suggestion")),
                message=c.get("message", c.get("comment", "")),
                suggested_fix=c.get("suggested_fix", c.get("suggestion")),
                code_snippet=c.get("code_snippet", ""),
            ))
        return CodeReviewResult(
            pr_info=pr_info,
            overall_assessment=data.get("overall_assessment", "comment"),
            summary=data.get("summary", "Review completed"),
            comments=comments,
            highlights=data.get("highlights", []),
            ast_insights=data.get("ast_insights", ""),
            reviewed_at=datetime.utcnow(),
        )

    async def close(self):
        """Close the model client to release resources."""
        if self._model_client:
            try:
                await self._model_client.close()
            except Exception:
                pass
            self._model_client = None


# ════════════════════════════════════════════════════════════════
#  Singleton
# ════════════════════════════════════════════════════════════════

_analyzer: Optional[AutoGenAnalyzer] = None


def get_autogen_analyzer() -> AutoGenAnalyzer:
    """Get or create the AutoGen analyzer singleton."""
    global _analyzer
    if _analyzer is None:
        _analyzer = AutoGenAnalyzer()
    return _analyzer
