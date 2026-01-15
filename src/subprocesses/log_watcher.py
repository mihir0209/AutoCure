"""
Log Watcher Subprocess (subprocess1)
Monitors log files for errors and warnings.
"""

import asyncio
import re
from pathlib import Path
from typing import AsyncGenerator, Optional, List
from datetime import datetime
import aiofiles

from utils.logger import setup_colored_logger
from utils.models import LogEntry, ErrorInfo, ErrorSeverity, LogLevel

logger = setup_colored_logger("log_watcher")


class LogWatcher:
    """
    Watches log files for errors and warnings.
    Yields ErrorInfo objects when errors are detected.
    
    subprocess1 -> watch logs -> 
        1. continues without errors -> do nothing
        2. error/warning -> subprocess3 (error processor)
    """
    
    # Patterns to detect errors
    ERROR_PATTERNS = [
        # Node.js/JavaScript errors
        r"Error:\s*(.+)",
        r"TypeError:\s*(.+)",
        r"ReferenceError:\s*(.+)",
        r"SyntaxError:\s*(.+)",
        r"RangeError:\s*(.+)",
        r"UnhandledPromiseRejection:\s*(.+)",
        # General errors
        r"\[ERROR\]\s*(.+)",
        r"FATAL:\s*(.+)",
        r"Exception:\s*(.+)",
        r"Traceback \(most recent call last\)",
    ]
    
    # Stack trace pattern
    STACK_TRACE_PATTERN = r"at\s+(?:(.+?)\s+)?\(?(.+?):(\d+):(\d+)\)?"
    
    def __init__(
        self,
        log_file: Path,
        watch_interval: float = 1.0,
        buffer_size: int = 100,
    ):
        self.log_file = log_file
        self.watch_interval = watch_interval
        self.buffer_size = buffer_size
        self.running = False
        self._last_position = 0
        self._error_buffer: List[str] = []
        self._compiled_patterns = [re.compile(p, re.IGNORECASE) for p in self.ERROR_PATTERNS]
        self._stack_pattern = re.compile(self.STACK_TRACE_PATTERN)
        
    def stop(self):
        """Stop watching"""
        self.running = False
        
    async def watch(self) -> AsyncGenerator[Optional[ErrorInfo], None]:
        """
        Watch the log file and yield ErrorInfo when errors are detected.
        
        Yields:
            ErrorInfo object when an error is detected, None otherwise
        """
        self.running = True
        logger.info(f"Starting log watch on: {self.log_file}")
        
        # Ensure log file exists
        self.log_file.parent.mkdir(parents=True, exist_ok=True)
        if not self.log_file.exists():
            self.log_file.touch()
        
        # Start from end of file
        self._last_position = self.log_file.stat().st_size
        
        while self.running:
            try:
                error_info = await self._check_for_new_logs()
                if error_info:
                    yield error_info
                await asyncio.sleep(self.watch_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Error watching logs: {e}")
                await asyncio.sleep(self.watch_interval)
        
        logger.info("Log watcher stopped")
    
    async def _check_for_new_logs(self) -> Optional[ErrorInfo]:
        """Check for new log entries and parse for errors"""
        try:
            current_size = self.log_file.stat().st_size
            
            if current_size < self._last_position:
                # File was truncated, start from beginning
                self._last_position = 0
            
            if current_size == self._last_position:
                return None
            
            # Read new content
            async with aiofiles.open(self.log_file, 'r', encoding='utf-8', errors='replace') as f:
                await f.seek(self._last_position)
                new_content = await f.read()
                self._last_position = current_size
            
            if not new_content.strip():
                return None
            
            # Parse new lines
            lines = new_content.strip().split('\n')
            return await self._parse_logs(lines)
            
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.error(f"Error reading log file: {e}")
            return None
    
    async def _parse_logs(self, lines: List[str]) -> Optional[ErrorInfo]:
        """Parse log lines and detect errors"""
        error_lines: List[str] = []
        in_error_block = False
        
        for line in lines:
            # Check if line matches error patterns
            is_error_line = any(p.search(line) for p in self._compiled_patterns)
            is_stack_line = self._stack_pattern.search(line) is not None
            
            if is_error_line:
                in_error_block = True
                error_lines.append(line)
                logger.warning(f"Error detected: {line[:100]}...")
            elif in_error_block and (is_stack_line or line.strip().startswith('at ')):
                error_lines.append(line)
            elif in_error_block and not line.strip():
                # End of error block
                if error_lines:
                    return self._create_error_info(error_lines)
                in_error_block = False
                error_lines = []
            elif is_stack_line:
                error_lines.append(line)
                in_error_block = True
        
        # Handle error block at end of file
        if error_lines:
            return self._create_error_info(error_lines)
        
        return None
    
    def _create_error_info(self, error_lines: List[str]) -> ErrorInfo:
        """Create ErrorInfo from collected error lines"""
        full_error = '\n'.join(error_lines)
        
        # Extract error type and message
        error_type = "UnknownError"
        message = full_error.split('\n')[0] if error_lines else "Unknown error"
        
        for pattern in self._compiled_patterns:
            match = pattern.search(error_lines[0] if error_lines else "")
            if match:
                if "TypeError" in error_lines[0]:
                    error_type = "TypeError"
                elif "ReferenceError" in error_lines[0]:
                    error_type = "ReferenceError"
                elif "SyntaxError" in error_lines[0]:
                    error_type = "SyntaxError"
                elif "Error:" in error_lines[0]:
                    error_type = "Error"
                message = match.group(1) if match.groups() else error_lines[0]
                break
        
        # Extract source file and line from stack trace
        source_file = "unknown"
        line_number = 0
        
        for line in error_lines:
            stack_match = self._stack_pattern.search(line)
            if stack_match:
                # Get the file path and line number
                file_path = stack_match.group(2)
                if file_path and not file_path.startswith('node:'):
                    source_file = file_path
                    line_number = int(stack_match.group(3)) if stack_match.group(3) else 0
                    break
        
        # Determine severity
        severity = ErrorSeverity.MEDIUM
        if "FATAL" in full_error.upper() or "CRITICAL" in full_error.upper():
            severity = ErrorSeverity.CRITICAL
        elif "TypeError" in error_type or "ReferenceError" in error_type:
            severity = ErrorSeverity.HIGH
        
        return ErrorInfo(
            error_type=error_type,
            message=message,
            stack_trace=full_error,
            source_file=source_file,
            line_number=line_number,
            severity=severity,
            timestamp=datetime.now(),
        )
