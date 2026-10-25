"""
AutoCure Healing Module
=======================
Minimal-Diff AST Patch Generator, Cascading Multi-File Patcher,
Regression Verifier, Transactional Auto-Rollback Engine & Fault Boundary Synthesizer.
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

__all__ = [
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
