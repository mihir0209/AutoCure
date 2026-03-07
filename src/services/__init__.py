"""
Services module for the Self-Healing Software System v2.0

Contains:
- log_analyzer: Parse and analyze incoming logs
- ast_service: AST building and analysis using tree-sitter
- github_service: GitHub/GitLab repository operations
- error_replicator: Replicate errors with payload variations
- ai_analyzer: AI-powered root cause analysis and code review
- email_service: Rich HTML email notifications
- report_store (via database.report_store): SQLite-backed HTML report index
"""

from .log_analyzer import LogAnalyzer
from .ast_service import ASTService
from .github_service import GitHubService
from .error_replicator import ErrorReplicator
from .ai_analyzer import AIAnalyzer
try:
    from .autogen_analyzer import AutoGenAnalyzer, get_autogen_analyzer
except ImportError:
    AutoGenAnalyzer = None  # type: ignore
    get_autogen_analyzer = None  # type: ignore
from .email_service import EmailService
from .ast_trace_service import ASTTraceService, get_ast_trace_service
from .confidence_validator import ConfidenceValidator, get_confidence_validator


# Singleton instances (lazy initialization)
_log_analyzer = None
_ast_service = None
_github_service = None
_error_replicator = None
_ai_analyzer = None
_email_service = None


def get_log_analyzer() -> LogAnalyzer:
    global _log_analyzer
    if _log_analyzer is None:
        _log_analyzer = LogAnalyzer()
    return _log_analyzer


def get_ast_service() -> ASTService:
    global _ast_service
    if _ast_service is None:
        _ast_service = ASTService()
    return _ast_service


def get_github_service() -> GitHubService:
    global _github_service
    if _github_service is None:
        from config import get_config
        config = get_config()
        _github_service = GitHubService(
            repos_base_path=config.github.repos_base_path,
            default_token=config.github.default_token
        )
    return _github_service


def get_error_replicator() -> ErrorReplicator:
    global _error_replicator
    if _error_replicator is None:
        _error_replicator = ErrorReplicator()
    return _error_replicator


def get_ai_analyzer() -> AIAnalyzer:
    """Returns the AI analyzer (uses Azure OpenAI / Groq / Cerebras based on config)."""
    global _ai_analyzer
    if _ai_analyzer is None:
        _ai_analyzer = AIAnalyzer()
    return _ai_analyzer


def get_email_service() -> EmailService:
    global _email_service
    if _email_service is None:
        _email_service = EmailService()
    return _email_service


__all__ = [
    "LogAnalyzer",
    "ASTService",
    "GitHubService",
    "ErrorReplicator",
    "AIAnalyzer",
    "AutoGenAnalyzer",
    "EmailService",
    "ASTTraceService",
    "ConfidenceValidator",
    "get_log_analyzer",
    "get_ast_service",
    "get_github_service",
    "get_error_replicator",
    "get_ai_analyzer",
    "get_email_service",
    "get_ast_trace_service",
    "get_confidence_validator",
]
