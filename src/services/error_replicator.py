"""
Error Replicator Service for the Self-Healing Software System v2.0

Attempts to replicate detected errors by making API calls with:
- The original payload
- Modified payloads (edge cases, null values, etc.)
- All calls include the "autocure-try": true flag

This helps determine:
- If the error is consistently reproducible
- What input variations trigger the error
- The error's root cause pattern
"""

import asyncio
from typing import Optional, List, Dict, Any
from datetime import datetime
import aiohttp
import json

from utils.models import (
    DetectedError, APIReplicationRequest, APIReplicationResult,
    ErrorReplicationSummary
)
from utils.logger import setup_colored_logger


logger = setup_colored_logger("error_replicator")


class ErrorReplicator:
    """
    Service for replicating errors by making API calls.
    
    Features:
    - Replicate exact error condition
    - Generate payload variations (null, empty, edge cases)
    - Mark all requests with autocure-try flag
    - Collect and analyze results
    """
    
    # Common payload variations to test
    VARIATION_STRATEGIES = [
        "original",          # Use original payload
        "null_values",       # Replace values with null
        "empty_strings",     # Replace strings with empty string
        "empty_arrays",      # Replace arrays with empty arrays
        "type_mismatch",     # Change types (string to int, etc.)
        "missing_fields",    # Remove optional fields
        "extra_fields",      # Add unexpected fields
        "boundary_values",   # Use boundary values (0, -1, MAX_INT)
    ]
    
    def __init__(self, base_url: Optional[str] = None, timeout: int = 10):
        """
        Initialize the error replicator.
        
        Args:
            base_url: Base URL for the user's service (if not in error)
            timeout: Request timeout in seconds
        """
        self.base_url = base_url
        self.timeout = timeout
        self.session: Optional[aiohttp.ClientSession] = None
        
    async def __aenter__(self):
        """Async context manager entry."""
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.timeout)
        )
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Async context manager exit."""
        if self.session:
            await self.session.close()
    
    async def replicate_error(
        self, error: DetectedError, base_url: Optional[str] = None
    ) -> ErrorReplicationSummary:
        """
        Attempt to replicate an error with various payload variations.
        
        Args:
            error: The detected error to replicate
            base_url: Base URL for the API (overrides instance default)
            
        Returns:
            Summary of replication attempts
        """
        base_url = base_url or self.base_url
        
        if not error.api_endpoint:
            logger.warning("No API endpoint in error - cannot replicate")
            return ErrorReplicationSummary(
                error=error,
                results=[],
                is_reproducible=False,
                reproduction_rate=0.0,
                error_patterns=[],
            )
        
        if not base_url:
            logger.warning("No base URL provided - cannot replicate")
            return ErrorReplicationSummary(
                error=error,
                results=[],
                is_reproducible=False,
                reproduction_rate=0.0,
                error_patterns=[],
            )
        
        results: List[APIReplicationResult] = []
        
        # Generate replication requests
        requests = self._generate_replication_requests(error, base_url)
        
        logger.info(f"Replicating error with {len(requests)} variations...")
        
        # Execute requests
        if not self.session:
            async with aiohttp.ClientSession(
                timeout=aiohttp.ClientTimeout(total=self.timeout)
            ) as session:
                results = await self._execute_requests(session, requests)
        else:
            results = await self._execute_requests(self.session, requests)
        
        # Analyze results
        summary = self._analyze_results(error, results)
        
        return summary
    
    def _generate_replication_requests(
        self, error: DetectedError, base_url: str
    ) -> List[APIReplicationRequest]:
        """Generate replication requests with various payload variations."""
        
        requests = []
        original_payload = error.payload or {}
        
        for strategy in self.VARIATION_STRATEGIES:
            payload = self._apply_variation(original_payload, strategy)
            
            # Add autocure-try flag
            if isinstance(payload, dict):
                payload["autocure-try"] = True
            
            url = f"{base_url.rstrip('/')}{error.api_endpoint}"
            
            requests.append(APIReplicationRequest(
                url=url,
                method=error.http_method or "GET",
                payload=payload,
                headers={"Content-Type": "application/json"},
                variation_type=strategy,
            ))
        
        return requests
    
    def _apply_variation(
        self, original: Any, strategy: str
    ) -> Any:
        """Apply a variation strategy to a payload."""
        
        if strategy == "original":
            return dict(original) if isinstance(original, dict) else original
        
        if not isinstance(original, dict):
            return original
        
        payload = dict(original)
        
        if strategy == "null_values":
            return {k: None for k in payload.keys()}
        
        elif strategy == "empty_strings":
            return {
                k: "" if isinstance(v, str) else v
                for k, v in payload.items()
            }
        
        elif strategy == "empty_arrays":
            return {
                k: [] if isinstance(v, list) else v
                for k, v in payload.items()
            }
        
        elif strategy == "type_mismatch":
            result = {}
            for k, v in payload.items():
                if isinstance(v, str):
                    result[k] = 0
                elif isinstance(v, (int, float)):
                    result[k] = str(v)
                elif isinstance(v, bool):
                    result[k] = "true" if v else "false"
                elif isinstance(v, list):
                    result[k] = {}
                elif isinstance(v, dict):
                    result[k] = []
                else:
                    result[k] = v
            return result
        
        elif strategy == "missing_fields":
            # Remove half the fields
            keys = list(payload.keys())
            return {k: payload[k] for k in keys[::2]}
        
        elif strategy == "extra_fields":
            payload["__unexpected_field"] = "test"
            payload["__random_number"] = 12345
            return payload
        
        elif strategy == "boundary_values":
            result = {}
            for k, v in payload.items():
                if isinstance(v, int):
                    result[k] = 0  # Could also try -1, MAX_INT
                elif isinstance(v, str):
                    result[k] = "a" * 10000  # Very long string
                elif isinstance(v, list):
                    result[k] = list(v) * 100  # Many items
                else:
                    result[k] = v
            return result
        
        return payload
    
    async def _execute_requests(
        self, session: aiohttp.ClientSession, requests: List[APIReplicationRequest]
    ) -> List[APIReplicationResult]:
        """Execute replication requests."""
        
        results = []
        
        for req in requests:
            result = await self._execute_single_request(session, req)
            results.append(result)
            
            # Small delay to avoid overwhelming the service
            await asyncio.sleep(0.1)
        
        return results
    
    async def _execute_single_request(
        self, session: aiohttp.ClientSession, request: APIReplicationRequest
    ) -> APIReplicationResult:
        """Execute a single replication request."""
        
        start_time = datetime.utcnow()
        
        try:
            method = request.method.upper()
            
            if method == "GET":
                async with session.get(
                    request.url, 
                    params=request.payload if isinstance(request.payload, dict) else None,
                    headers=request.headers,
                ) as response:
                    return await self._process_response(request, response, start_time)
            
            elif method in ["POST", "PUT", "PATCH"]:
                async with session.request(
                    method,
                    request.url,
                    json=request.payload,
                    headers=request.headers,
                ) as response:
                    return await self._process_response(request, response, start_time)
            
            elif method == "DELETE":
                async with session.delete(
                    request.url,
                    headers=request.headers,
                ) as response:
                    return await self._process_response(request, response, start_time)
            
            else:
                return APIReplicationResult(
                    request=request,
                    success=False,
                    status_code=0,
                    response_body="Unsupported HTTP method",
                    error_reproduced=False,
                    response_time_ms=0,
                )
                
        except asyncio.TimeoutError:
            return APIReplicationResult(
                request=request,
                success=False,
                status_code=0,
                response_body="Request timed out",
                error_reproduced=True,  # Timeout could indicate the same issue
                response_time_ms=self.timeout * 1000,
            )
            
        except aiohttp.ClientError as e:
            return APIReplicationResult(
                request=request,
                success=False,
                status_code=0,
                response_body=str(e),
                error_reproduced=True,  # Connection error could indicate issue
                response_time_ms=int((datetime.utcnow() - start_time).total_seconds() * 1000),
            )
            
        except Exception as e:
            return APIReplicationResult(
                request=request,
                success=False,
                status_code=0,
                response_body=f"Unexpected error: {str(e)}",
                error_reproduced=False,
                response_time_ms=int((datetime.utcnow() - start_time).total_seconds() * 1000),
            )
    
    async def _process_response(
        self, request: APIReplicationRequest, response: aiohttp.ClientResponse, 
        start_time: datetime
    ) -> APIReplicationResult:
        """Process an HTTP response."""
        
        response_time = int((datetime.utcnow() - start_time).total_seconds() * 1000)
        
        try:
            body = await response.text()
        except Exception:
            body = ""
        
        # Consider 4xx and 5xx as error reproduction
        is_error = response.status >= 400
        
        return APIReplicationResult(
            request=request,
            success=response.status < 400,
            status_code=response.status,
            response_body=body[:5000],  # Limit response size
            error_reproduced=is_error,
            response_time_ms=response_time,
        )
    
    def _analyze_results(
        self, error: DetectedError, results: List[APIReplicationResult]
    ) -> ErrorReplicationSummary:
        """Analyze replication results."""
        
        if not results:
            return ErrorReplicationSummary(
                error=error,
                results=results,
                is_reproducible=False,
                reproduction_rate=0.0,
                error_patterns=[],
            )
        
        # Count reproduced errors
        reproduced = sum(1 for r in results if r.error_reproduced)
        reproduction_rate = reproduced / len(results)
        
        # Identify patterns
        patterns = []
        
        # Group by status code
        status_counts: Dict[int, int] = {}
        for r in results:
            status_counts[r.status_code] = status_counts.get(r.status_code, 0) + 1
        
        for status, count in status_counts.items():
            if count > 1 and status >= 400:
                patterns.append(f"HTTP {status} occurred {count} times")
        
        # Check which variations reproduced the error
        reproducing_variations = [
            r.request.variation_type for r in results if r.error_reproduced
        ]
        
        if "original" in reproducing_variations:
            patterns.append("Error reproduced with original payload")
        
        if "null_values" in reproducing_variations:
            patterns.append("Error triggered by null values - possible null reference issue")
        
        if "empty_strings" in reproducing_variations:
            patterns.append("Error triggered by empty strings - possible validation issue")
        
        if "type_mismatch" in reproducing_variations:
            patterns.append("Error triggered by type mismatch - possible type validation issue")
        
        return ErrorReplicationSummary(
            error=error,
            results=results,
            is_reproducible=reproduced > 0,
            reproduction_rate=reproduction_rate,
            error_patterns=patterns,
        )


# Singleton instance
_replicator: Optional[ErrorReplicator] = None


def get_error_replicator() -> ErrorReplicator:
    """Get or create the error replicator singleton."""
    global _replicator
    if _replicator is None:
        _replicator = ErrorReplicator()
    return _replicator
