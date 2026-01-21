"""
Log Analyzer Service for the Self-Healing Software System v2.0

Parses incoming logs from WebSocket connections, detects errors,
and extracts relevant information for analysis including:
- API endpoint and HTTP method
- Request payload
- Stack trace parsing
- Error categorization
"""

import re
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime
from pydantic import BaseModel

from utils.models import LogEntry, DetectedError, ASTContext
from utils.logger import setup_colored_logger


logger = setup_colored_logger("log_analyzer")


class LogAnalyzer:
    """
    Analyzes log entries to detect and categorize errors.
    
    Features:
    - Stack trace parsing for multiple languages (JavaScript, Python, Java)
    - API endpoint extraction from request logs
    - Payload extraction from log messages
    - Error categorization (runtime, syntax, network, etc.)
    - Autocure-try flag detection
    """
    
    # Common error patterns
    ERROR_PATTERNS = {
        "javascript": [
            r"TypeError:\s+(.+)",
            r"ReferenceError:\s+(.+)",
            r"SyntaxError:\s+(.+)",
            r"RangeError:\s+(.+)",
            r"Error:\s+(.+)",
            r"Uncaught\s+(\w+Error):\s+(.+)",
        ],
        "python": [
            r"(\w+Error):\s+(.+)",
            r"(\w+Exception):\s+(.+)",
            r"Traceback \(most recent call last\)",
        ],
        "java": [
            r"(\w+Exception):\s+(.+)",
            r"(\w+Error):\s+(.+)",
            r"at\s+[\w.$]+\([\w.]+:\d+\)",
        ],
    }
    
    # Stack trace patterns
    STACK_PATTERNS = {
        "javascript": r"at\s+(?:(\w+)\s+)?\(?([^:]+):(\d+):(\d+)\)?",
        "python": r'File\s+"([^"]+)",\s+line\s+(\d+)',
        "java": r"at\s+([\w.$]+)\(([\w.]+):(\d+)\)",
    }
    
    # API endpoint patterns
    API_PATTERNS = [
        r'(GET|POST|PUT|DELETE|PATCH|OPTIONS|HEAD)\s+([^\s]+)',
        r'"(GET|POST|PUT|DELETE|PATCH)"\s+"([^"]+)"',
        r'method["\']?\s*[:=]\s*["\']?(GET|POST|PUT|DELETE|PATCH)',
        r'url["\']?\s*[:=]\s*["\']?([^\s"\']+)',
        r'endpoint["\']?\s*[:=]\s*["\']?([^\s"\']+)',
    ]
    
    def __init__(self):
        self.recent_logs: List[LogEntry] = []
        self.detected_errors: List[DetectedError] = []
        
    def analyze_log(self, log: LogEntry) -> Optional[DetectedError]:
        """
        Analyze a single log entry for errors.
        
        Returns a DetectedError if an error is detected, None otherwise.
        """
        self.recent_logs.append(log)
        
        # Keep only last 500 logs for context
        if len(self.recent_logs) > 500:
            self.recent_logs = self.recent_logs[-500:]
        
        # Check if this is an error log
        if log.level.upper() not in ["ERROR", "FATAL", "CRITICAL", "EXCEPTION"]:
            return None
        
        # Detect language from stack trace or file extension
        language = self._detect_language(log.message, log.stack_trace)
        
        # Parse stack trace
        source_file, line_number, function_name = self._parse_stack_trace(
            log.stack_trace or log.message, language
        )
        
        # Extract API information
        http_method, api_endpoint = self._extract_api_info(log)
        
        # Categorize error
        error_type, error_category = self._categorize_error(log.message, language)
        
        # Check for autocure-try flag
        is_autocure_try = self._check_autocure_flag(log)
        
        # Create detected error
        detected_error = DetectedError(
            timestamp=log.timestamp,
            error_type=error_type,
            error_category=error_category,
            message=log.message,
            stack_trace=log.stack_trace,
            source_file=source_file,
            line_number=line_number,
            function_name=function_name,
            api_endpoint=api_endpoint,
            http_method=http_method,
            payload=log.payload,
            is_autocure_try=is_autocure_try,
            language=language,
            raw_log=log,
        )
        
        self.detected_errors.append(detected_error)
        
        logger.info(f"✓ Detected error: {error_type} at {source_file}:{line_number}")
        
        return detected_error
    
    def _detect_language(self, message: str, stack_trace: Optional[str]) -> str:
        """Detect the programming language from error message or stack trace."""
        text = f"{message} {stack_trace or ''}"
        
        # JavaScript indicators
        if any(x in text for x in ["TypeError:", "ReferenceError:", ".js:", "node_modules"]):
            return "javascript"
        
        # Python indicators
        if any(x in text for x in ["Traceback", ".py:", "File \"", "line "]):
            return "python"
        
        # Java indicators
        if any(x in text for x in [".java:", "at com.", "at org.", "Exception:", "NullPointerException"]):
            return "java"
        
        return "unknown"
    
    def _parse_stack_trace(
        self, text: str, language: str
    ) -> Tuple[Optional[str], Optional[int], Optional[str]]:
        """Parse stack trace to extract source file, line number, and function name."""
        
        if language == "javascript":
            # Match: at functionName (file.js:10:20) or at file.js:10:20
            pattern = self.STACK_PATTERNS["javascript"]
            matches = re.findall(pattern, text)
            if matches:
                # Get the first non-node_modules match if possible
                for match in matches:
                    func_name, file_path, line, col = match
                    if "node_modules" not in file_path:
                        return file_path, int(line), func_name or None
                # Fallback to first match
                if matches:
                    func_name, file_path, line, col = matches[0]
                    return file_path, int(line), func_name or None
                    
        elif language == "python":
            # Match: File "path/file.py", line 10
            pattern = self.STACK_PATTERNS["python"]
            matches = re.findall(pattern, text)
            if matches:
                # Get the last match (usually the actual error location)
                file_path, line = matches[-1]
                return file_path, int(line), None
                
        elif language == "java":
            # Match: at package.Class.method(File.java:10)
            pattern = self.STACK_PATTERNS["java"]
            matches = re.findall(pattern, text)
            if matches:
                for match in matches:
                    full_method, file_name, line = match
                    method_name = full_method.split(".")[-1]
                    return file_name, int(line), method_name
        
        return None, None, None
    
    def _extract_api_info(self, log: LogEntry) -> Tuple[Optional[str], Optional[str]]:
        """Extract HTTP method and API endpoint from log."""
        
        # First check if the log has explicit fields
        if log.api_endpoint:
            return log.http_method, log.api_endpoint
        
        # Try to extract from message
        text = f"{log.message} {log.metadata or ''}"
        
        for pattern in self.API_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                groups = match.groups()
                if len(groups) == 2:
                    return groups[0].upper(), groups[1]
                elif len(groups) == 1:
                    if groups[0].upper() in ["GET", "POST", "PUT", "DELETE", "PATCH"]:
                        return groups[0].upper(), None
                    else:
                        return None, groups[0]
        
        return None, None
    
    def _categorize_error(self, message: str, language: str) -> Tuple[str, str]:
        """Categorize the error type and category."""
        
        message_lower = message.lower()
        
        # Extract error type from message
        error_type = "UnknownError"
        for lang_patterns in self.ERROR_PATTERNS.values():
            for pattern in lang_patterns:
                match = re.search(pattern, message)
                if match:
                    error_type = match.group(1) if match.lastindex else "Error"
                    break
        
        # Determine category
        if any(x in message_lower for x in ["undefined", "null", "none", "nil"]):
            category = "null_reference"
        elif any(x in message_lower for x in ["type", "cannot read", "is not"]):
            category = "type_error"
        elif any(x in message_lower for x in ["syntax", "unexpected token", "parse"]):
            category = "syntax_error"
        elif any(x in message_lower for x in ["timeout", "timed out", "deadline"]):
            category = "timeout"
        elif any(x in message_lower for x in ["connection", "network", "refused", "unreachable"]):
            category = "network_error"
        elif any(x in message_lower for x in ["permission", "denied", "unauthorized", "forbidden"]):
            category = "permission_error"
        elif any(x in message_lower for x in ["not found", "404", "missing"]):
            category = "not_found"
        elif any(x in message_lower for x in ["memory", "heap", "allocation"]):
            category = "memory_error"
        else:
            category = "runtime_error"
        
        return error_type, category
    
    def _check_autocure_flag(self, log: LogEntry) -> bool:
        """Check if the log contains the autocure-try flag."""
        
        # Check in payload
        if log.payload:
            if isinstance(log.payload, dict):
                return log.payload.get("autocure-try", False) is True
            elif isinstance(log.payload, str):
                return '"autocure-try": true' in log.payload or "'autocure-try': True" in log.payload
        
        # Check in message
        if "autocure-try" in log.message.lower():
            return True
        
        # Check in metadata
        if log.metadata:
            if isinstance(log.metadata, dict):
                return log.metadata.get("autocure-try", False) is True
        
        return False
    
    def get_context_logs(
        self, error: DetectedError, before: int = 20, after: int = 5
    ) -> List[LogEntry]:
        """Get surrounding log entries for context."""
        
        try:
            error_index = self.recent_logs.index(error.raw_log)
            start = max(0, error_index - before)
            end = min(len(self.recent_logs), error_index + after + 1)
            return self.recent_logs[start:end]
        except (ValueError, AttributeError):
            return []
    
    def get_related_errors(
        self, error: DetectedError, window_seconds: int = 60
    ) -> List[DetectedError]:
        """Get related errors that occurred around the same time."""
        
        related = []
        for e in self.detected_errors:
            if e == error:
                continue
            time_diff = abs((error.timestamp - e.timestamp).total_seconds())
            if time_diff <= window_seconds:
                # Check if they might be related
                if (e.source_file == error.source_file or 
                    e.api_endpoint == error.api_endpoint or
                    e.error_type == error.error_type):
                    related.append(e)
        
        return related
    
    def clear_old_data(self, max_age_hours: int = 24):
        """Clear old logs and errors to prevent memory issues."""
        
        cutoff = datetime.utcnow().timestamp() - (max_age_hours * 3600)
        
        self.recent_logs = [
            log for log in self.recent_logs 
            if log.timestamp.timestamp() > cutoff
        ]
        
        self.detected_errors = [
            error for error in self.detected_errors 
            if error.timestamp.timestamp() > cutoff
        ]
