"""
AutoCure Healing Module
=======================
Minimal-Diff AST Patch Generator, Cascading Multi-File Patcher,
Regression Verifier, Transactional Auto-Rollback Engine, Fault Boundary Synthesizer,
Async/Await Deadlock Sanitizer, SQL Injection Parameterizer, Import Cycle Breaker,
Session/Executor Sanitizer, ReDoS Safe Regex Synthesizer, Path Traversal Sanitizer,
Stream Memory Exhaustion Sanitizer, SSRF Sanitizer, Deserialization Sanitizer,
Crypto Sanitizer, Command Injection Sanitizer, XXE Sanitizer, and Secrets Extractor.
"""

from .ast_patcher import ASTPatcher, ASTPatch, DefectPattern
from .cascading_patcher import (
    CascadingASTPatcher,
    CascadingHealResult,
    CallSiteMatch,
    TransactionSnapshot,
)
from .verifier import RegressionVerifier, VerificationResult
from .null_safety_synthesizer import NullSafetyFinding, NullSafetySynthesizer, synthesize_null_safety
from .resource_leak_synthesizer import ResourceLeakFinding, ResourceLeakSynthesizer, synthesize_resource_management
from .exception_boundary_synthesizer import (
    ExceptionBoundaryFinding,
    ExceptionBoundarySynthesizer,
    synthesize_exception_boundaries,
)
from .async_deadlock_sanitizer import (
    AsyncDeadlockFinding,
    AsyncDeadlockSanitizer,
    sanitize_async_deadlocks,
)
from .invariant_guard_synthesizer import (
    InvariantViolationFinding,
    InvariantGuardSynthesizer,
    synthesize_invariant_guards,
)
from .sql_injection_synthesizer import (
    SQLInjectionFinding,
    SQLInjectionSynthesizer,
    synthesize_parameterized_queries,
)
from .import_cycle_synthesizer import (
    ImportCycleFinding,
    ImportCycleSynthesizer,
    synthesize_import_cycle_break,
)
from .executor_session_sanitizer import (
    ExecutorSessionFinding,
    ExecutorSessionSanitizer,
    sanitize_executor_sessions,
)
from .redos_synthesizer import (
    ReDoSFinding,
    ReDoSSynthesizer,
    synthesize_redos_guards,
)
from .path_traversal_sanitizer import (
    PathTraversalFinding,
    PathTraversalSanitizer,
    sanitize_path_traversal,
)
from .stream_memory_sanitizer import (
    StreamMemoryFinding,
    StreamMemorySanitizer,
    sanitize_stream_memory,
)
from .ssrf_sanitizer import (
    SSRFFinding,
    SSRFSanitizer,
    sanitize_ssrf,
)
from .deserialization_sanitizer import (
    DeserializationFinding,
    DeserializationSanitizer,
    sanitize_deserialization,
)
from .crypto_sanitizer import (
    CryptoFinding,
    CryptoSanitizer,
    sanitize_crypto,
)
from .command_injection_sanitizer import (
    CommandInjectionFinding,
    CommandInjectionSanitizer,
    sanitize_command_injection,
)
from .xxe_sanitizer import (
    XXEFinding,
    XXESanitizer,
    sanitize_xxe,
)
from .secrets_sanitizer import (
    SecretFinding,
    SecretsSanitizer,
    sanitize_secrets,
)

__all__ = [
    "CommandInjectionFinding",
    "CommandInjectionSanitizer",
    "sanitize_command_injection",
    "XXEFinding",
    "XXESanitizer",
    "sanitize_xxe",
    "SecretFinding",
    "SecretsSanitizer",
    "sanitize_secrets",
    "SQLInjectionFinding",
    "SQLInjectionSynthesizer",
    "synthesize_parameterized_queries",
    "ImportCycleFinding",
    "ImportCycleSynthesizer",
    "synthesize_import_cycle_break",
    "ExecutorSessionFinding",
    "ExecutorSessionSanitizer",
    "sanitize_executor_sessions",
    "ReDoSFinding",
    "ReDoSSynthesizer",
    "synthesize_redos_guards",
    "PathTraversalFinding",
    "PathTraversalSanitizer",
    "sanitize_path_traversal",
    "StreamMemoryFinding",
    "StreamMemorySanitizer",
    "sanitize_stream_memory",
    "SSRFFinding",
    "SSRFSanitizer",
    "sanitize_ssrf",
    "DeserializationFinding",
    "DeserializationSanitizer",
    "sanitize_deserialization",
    "CryptoFinding",
    "CryptoSanitizer",
    "sanitize_crypto",
    "InvariantViolationFinding",
    "InvariantGuardSynthesizer",
    "synthesize_invariant_guards",
    "AsyncDeadlockFinding",
    "AsyncDeadlockSanitizer",
    "sanitize_async_deadlocks",
    "ExceptionBoundaryFinding",
    "ExceptionBoundarySynthesizer",
    "synthesize_exception_boundaries",
    "ResourceLeakFinding",
    "ResourceLeakSynthesizer",
    "synthesize_resource_management",
    "NullSafetyFinding",
    "NullSafetySynthesizer",
    "synthesize_null_safety",
    "ASTPatcher",
    "ASTPatch",
    "DefectPattern",
    "CascadingASTPatcher",
    "CascadingHealResult",
    "CallSiteMatch",
    "TransactionSnapshot",
    "RegressionVerifier",
    "VerificationResult",
]
