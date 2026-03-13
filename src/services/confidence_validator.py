"""
Confidence Validator Service for the Self-Healing Software System v2.0

Implements multi-iteration validation with AI comparison:
- Run 5 payload variations to test error reproducibility
- Get AI analysis for each variation result
- Compare all 6 analyses (1 initial + 5 retries) 
- Calculate confidence score with 75% threshold
"""

from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field
from datetime import datetime

from utils.models import (
    DetectedError, RootCauseAnalysis, APIReplicationResult,
    ErrorReplicationSummary
)
from utils.logger import setup_colored_logger
from services.error_replicator import get_error_replicator

logger = setup_colored_logger("confidence_validator")


# ==========================================
# Data Models
# ==========================================

@dataclass
class ValidationIteration:
    """Result of a single validation iteration."""
    iteration_number: int
    payload_variation: str
    replication_result: Optional[APIReplicationResult] = None
    analysis: Optional[RootCauseAnalysis] = None
    matches_initial: bool = False
    notes: str = ""


@dataclass
class ValidationResult:
    """Complete validation result with confidence scoring."""
    error_id: str
    initial_analysis: RootCauseAnalysis
    iterations: List[ValidationIteration] = field(default_factory=list)
    replication_summary: Optional[ErrorReplicationSummary] = None
    
    # Confidence scoring
    confidence_score: float = 0.0
    confidence_met: bool = False  # >= 75%
    
    # Analysis comparison
    consistent_root_cause: str = ""
    divergent_findings: List[str] = field(default_factory=list)
    possible_causes: List[str] = field(default_factory=list)
    
    # Metadata
    total_iterations: int = 6  # 1 initial + 5 retries
    matching_iterations: int = 0
    validated_at: datetime = field(default_factory=datetime.now)


# ==========================================
# Confidence Validator Service
# ==========================================

CONFIDENCE_THRESHOLD = 75.0  # Minimum confidence to suggest fixes


class ConfidenceValidator:
    """
    Service for multi-iteration error validation with AI comparison.
    
    Implements the workflow:
    1. Initial error detection and AI analysis
    2. Generate 5 payload variations
    3. Run each variation and collect results
    4. Get AI analysis for each result
    5. Compare all 6 analyses
    6. Calculate overall confidence score
    7. If >= 75%: proceed with fix suggestions
    8. If < 75%: report possible causes only
    """
    
    def __init__(self, ai_analyzer=None, confidence_threshold: float = CONFIDENCE_THRESHOLD):
        """
        Initialize the confidence validator.
        
        Args:
            ai_analyzer: AI analyzer instance (lazy loaded if not provided)
            confidence_threshold: Minimum confidence to suggest fixes (default 75%)
        """
        self._ai_analyzer = ai_analyzer
        self.confidence_threshold = confidence_threshold
    
    @property
    def ai_analyzer(self):
        """Lazy load AI analyzer."""
        if self._ai_analyzer is None:
            from services.ai_analyzer import get_ai_analyzer
            self._ai_analyzer = get_ai_analyzer()
        return self._ai_analyzer
    
    async def validate_error(
        self,
        error: DetectedError,
        initial_analysis: RootCauseAnalysis,
        base_url: Optional[str] = None
    ) -> ValidationResult:
        """
        Run multi-iteration validation on a detected error.
        
        Args:
            error: The detected error to validate
            initial_analysis: The initial AI analysis of the error
            base_url: Base URL for error replication API calls
            
        Returns:
            ValidationResult with confidence score and analysis comparison
        """
        logger.info(f"Starting validation for error {error.error_id}")
        
        result = ValidationResult(
            error_id=error.error_id,
            initial_analysis=initial_analysis
        )
        
        # Skip validation if no API endpoint available
        if not error.api_endpoint:
            logger.warning("No API endpoint for replication - using initial analysis only")
            result.confidence_score = initial_analysis.confidence * 100
            result.confidence_met = result.confidence_score >= self.confidence_threshold
            result.consistent_root_cause = initial_analysis.root_cause
            return result
        
        # Run error replication with variations
        replicator = get_error_replicator()
        
        try:
            async with replicator:
                result.replication_summary = await replicator.replicate_error(
                    error, base_url
                )
        except Exception as e:
            logger.error(f"Replication failed: {e}")
            # Fall back to initial analysis
            result.confidence_score = initial_analysis.confidence * 100
            result.confidence_met = result.confidence_score >= self.confidence_threshold
            result.consistent_root_cause = initial_analysis.root_cause
            return result
        
        # Analyze each replication result
        if result.replication_summary:
            for i, rep_result in enumerate(result.replication_summary.results[:5]):
                iteration = ValidationIteration(
                    iteration_number=i + 1,
                    payload_variation=rep_result.request.variation_type,
                    replication_result=rep_result
                )
                
                # Get AI analysis for this result
                try:
                    iteration_analysis = await self._analyze_iteration(
                        error, rep_result, i + 1
                    )
                    iteration.analysis = iteration_analysis
                    
                    # Compare with initial analysis
                    iteration.matches_initial = self._analyses_match(
                        initial_analysis, iteration_analysis
                    )
                    
                    if iteration.matches_initial:
                        result.matching_iterations += 1
                        
                except Exception as e:
                    logger.error(f"Analysis failed for iteration {i + 1}: {e}")
                    iteration.notes = f"Analysis failed: {e}"
                
                result.iterations.append(iteration)
        
        # Calculate confidence score
        result = self._calculate_confidence(result)
        
        # Determine if fix suggestions should be made
        result.confidence_met = result.confidence_score >= self.confidence_threshold
        
        if result.confidence_met:
            logger.info(f"Confidence {result.confidence_score:.1f}% >= threshold - "
                       "will suggest fixes")
        else:
            logger.info(f"Confidence {result.confidence_score:.1f}% < threshold - "
                       "will report possible causes only")
            result.possible_causes = self._extract_possible_causes(result)
        
        return result
    
    async def _analyze_iteration(
        self,
        error: DetectedError,
        rep_result: APIReplicationResult,
        iteration: int
    ) -> RootCauseAnalysis:
        """Get AI analysis for a replication iteration."""
        
        # Create modified error based on replication result
        modified_error = DetectedError(
            error_id=f"{error.error_id}_iter{iteration}",
            error_type=error.error_type,
            message=rep_result.error_message or error.message,
            source_file=error.source_file,
            line_number=error.line_number,
            api_endpoint=error.api_endpoint,
            http_method=error.http_method,
            original_payload=rep_result.request.modified_payload
        )
        
        # Get AI analysis
        analysis = await self.ai_analyzer.analyze_error(
            error=modified_error,
            source_code=None,
            ast_context=None
        )
        
        return analysis
    
    def _analyses_match(
        self,
        initial: RootCauseAnalysis,
        iteration: RootCauseAnalysis
    ) -> bool:
        """
        Compare two analyses for consistency.
        
        Uses fuzzy matching on root cause description.
        """
        if not initial or not iteration:
            return False
        
        # Normalize root causes for comparison
        initial_cause = initial.root_cause.lower().strip()
        iter_cause = iteration.root_cause.lower().strip()
        
        # Check for exact match
        if initial_cause == iter_cause:
            return True
        
        # Check for significant overlap (>50% of words match)
        initial_words = set(initial_cause.split())
        iter_words = set(iter_cause.split())
        
        if len(initial_words) == 0:
            return False
        
        overlap = len(initial_words & iter_words) / len(initial_words)
        return overlap > 0.5
    
    def _calculate_confidence(self, result: ValidationResult) -> ValidationResult:
        """
        Calculate overall confidence score from validation results.
        
        Formula:
        - Initial analysis confidence: 40% weight
        - Matching iterations: 60% weight (12% per matching iteration out of 5)
        """
        initial_weight = 0.4
        iteration_weight = 0.6
        
        # Initial analysis contribution
        initial_confidence = result.initial_analysis.confidence or 0.5
        
        # Iteration contribution
        if len(result.iterations) > 0:
            match_ratio = result.matching_iterations / len(result.iterations)
        else:
            # No replication was possible — trust initial analysis as-is
            result.confidence_score = min(100.0, max(0.0, initial_confidence * 100))
            result.consistent_root_cause = result.initial_analysis.root_cause
            return result
        
        # Calculate weighted confidence
        confidence = (
            (initial_confidence * initial_weight) +
            (match_ratio * iteration_weight)
        ) * 100
        
        result.confidence_score = min(100.0, max(0.0, confidence))
        
        # Find consistent root cause
        if result.matching_iterations >= 3:  # Majority match
            result.consistent_root_cause = result.initial_analysis.root_cause
        else:
            # Find most common root cause across analyses
            result.consistent_root_cause = self._find_most_common_cause(result)
            result.divergent_findings = self._find_divergent_findings(result)
        
        return result
    
    def _find_most_common_cause(self, result: ValidationResult) -> str:
        """Find the most commonly identified root cause."""
        causes = [result.initial_analysis.root_cause]
        
        for iteration in result.iterations:
            if iteration.analysis:
                causes.append(iteration.analysis.root_cause)
        
        # Simple frequency count
        cause_counts = {}
        for cause in causes:
            normalized = cause.lower().strip()[:100]  # First 100 chars
            cause_counts[normalized] = cause_counts.get(normalized, 0) + 1
        
        if not cause_counts:
            return result.initial_analysis.root_cause
        
        most_common = max(cause_counts.items(), key=lambda x: x[1])
        return most_common[0]
    
    def _find_divergent_findings(self, result: ValidationResult) -> List[str]:
        """Find findings that differ from the initial analysis."""
        divergent = []
        initial_cause = result.initial_analysis.root_cause.lower()
        
        for iteration in result.iterations:
            if iteration.analysis and not iteration.matches_initial:
                cause = iteration.analysis.root_cause
                if cause.lower() not in initial_cause:
                    divergent.append(
                        f"Iteration {iteration.iteration_number} ({iteration.payload_variation}): "
                        f"{cause[:100]}"
                    )
        
        return divergent[:5]  # Limit to 5
    
    def _extract_possible_causes(self, result: ValidationResult) -> List[str]:
        """
        Extract possible causes when confidence is low.
        
        Used when we can't confidently identify the root cause.
        """
        possible = set()
        
        # Add initial analysis root cause
        possible.add(result.initial_analysis.root_cause)
        
        # Add causes from iterations
        for iteration in result.iterations:
            if iteration.analysis and iteration.analysis.root_cause:
                possible.add(iteration.analysis.root_cause)
        
        # Add affected components
        for comp in result.initial_analysis.affected_components:
            possible.add(f"Issue in component: {comp}")
        
        return list(possible)[:10]  # Limit to 10
    
    def should_suggest_fixes(self, result: ValidationResult) -> bool:
        """Check if fix suggestions should be made based on confidence."""
        return result.confidence_met
    
    def get_summary_for_email(self, result: ValidationResult) -> Dict[str, Any]:
        """
        Get a summary suitable for email reporting.
        
        Returns different content based on confidence level.
        """
        summary = {
            "confidence_score": result.confidence_score,
            "confidence_met": result.confidence_met,
            "total_iterations": len(result.iterations) + 1,
            "matching_iterations": result.matching_iterations + 1,  # Include initial
        }
        
        if result.confidence_met:
            summary["type"] = "high_confidence"
            summary["root_cause"] = result.consistent_root_cause
            summary["message"] = (
                f"High confidence ({result.confidence_score:.0f}%) in root cause identification. "
                f"Fix suggestions are provided below."
            )
        else:
            summary["type"] = "low_confidence"
            summary["possible_causes"] = result.possible_causes
            summary["divergent_findings"] = result.divergent_findings
            summary["message"] = (
                f"Confidence ({result.confidence_score:.0f}%) is below the {self.confidence_threshold}% "
                f"threshold required for fix suggestions. Possible causes are listed below."
            )
        
        return summary


# ==========================================
# Singleton
# ==========================================

_validator: Optional[ConfidenceValidator] = None


def get_confidence_validator() -> ConfidenceValidator:
    """Get or create the confidence validator singleton."""
    global _validator
    if _validator is None:
        _validator = ConfidenceValidator()
    return _validator
