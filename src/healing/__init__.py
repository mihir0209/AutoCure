"""
AutoCure Healing Module
=======================
Minimal-Diff AST Patch Generator, Cascading Multi-File Patcher,
Regression Verifier & Transactional Auto-Rollback Engine.
"""

from .ast_patcher import ASTPatcher, ASTPatch, DefectPattern
from .cascading_patcher import (
    CascadingASTPatcher,
    CascadingHealResult,
    CallSiteMatch,
    TransactionSnapshot,
)
from .verifier import RegressionVerifier, VerificationResult

__all__ = [
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
from .null_safety_synthesizer import NullSafetyFinding, NullSafetySynthesizer, synthesize_null_safety
