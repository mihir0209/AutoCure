"""
AutoCure Healing Module
=======================
Minimal-Diff AST Patch Generator, Regression Verifier & Auto-Rollback Engine.
"""

from .ast_patcher import ASTPatcher, ASTPatch, DefectPattern
from .verifier import RegressionVerifier, VerificationResult

__all__ = [
    "ASTPatcher",
    "ASTPatch",
    "DefectPattern",
    "RegressionVerifier",
    "VerificationResult",
]
