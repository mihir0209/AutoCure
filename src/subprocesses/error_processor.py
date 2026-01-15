"""
Error Processor Subprocess (subprocess3)
Traces errors to their source code origin.
"""

import re
from pathlib import Path
from typing import List, Optional, Tuple
import aiofiles

from utils.logger import setup_colored_logger
from utils.models import ErrorInfo, ErrorSeverity

logger = setup_colored_logger("error_processor")


class ErrorProcessor:
    """
    Processes log errors to trace them back to source code.
    
    subprocess3 -> process(logs) => output = traced till the start point of error
    (the starting point of that error, the code where this line is referenced from)
    """
    
    # Stack trace patterns for different languages
    STACK_PATTERNS = {
        'javascript': re.compile(r'at\s+(?:(.+?)\s+)?\(?(.+?):(\d+):(\d+)\)?'),
        'python': re.compile(r'File "(.+?)", line (\d+), in (.+)'),
    }
    
    def __init__(self, target_service_path: Path):
        self.target_service_path = target_service_path
        
    async def trace_error_origin(self, error_info: ErrorInfo) -> ErrorInfo:
        """
        Trace error to its origin in source code.
        Enriches ErrorInfo with context and related files.
        
        Args:
            error_info: Initial error information from log watcher
            
        Returns:
            Enriched ErrorInfo with source context
        """
        logger.info(f"Tracing error origin: {error_info.error_type}")
        
        # Parse stack trace to find all related files
        related_files = self._extract_related_files(error_info.stack_trace)
        error_info.related_files = related_files
        
        # Resolve source file path
        source_file = await self._resolve_source_file(error_info.source_file)
        if source_file:
            error_info.source_file = str(source_file)
            
            # Get source code context
            context_before, context_after = await self._get_code_context(
                source_file, 
                error_info.line_number
            )
            error_info.context_before = context_before
            error_info.context_after = context_after
        
        # Analyze root cause
        error_info.root_cause_analysis = await self._analyze_root_cause(error_info)
        
        logger.info(f"✓ Error traced to: {error_info.source_file}:{error_info.line_number}")
        logger.info(f"  Related files: {len(error_info.related_files)}")
        
        return error_info
    
    def _extract_related_files(self, stack_trace: str) -> List[str]:
        """Extract all file references from stack trace"""
        related_files = []
        
        # Try JavaScript pattern
        for match in self.STACK_PATTERNS['javascript'].finditer(stack_trace):
            file_path = match.group(2)
            if file_path and not file_path.startswith('node:'):
                related_files.append(file_path)
        
        # Try Python pattern
        for match in self.STACK_PATTERNS['python'].finditer(stack_trace):
            file_path = match.group(1)
            if file_path:
                related_files.append(file_path)
        
        # Remove duplicates while preserving order
        seen = set()
        unique_files = []
        for f in related_files:
            if f not in seen:
                seen.add(f)
                unique_files.append(f)
        
        return unique_files
    
    async def _resolve_source_file(self, file_path: str) -> Optional[Path]:
        """Resolve file path to actual file in target service"""
        if not file_path or file_path == "unknown":
            return None
        
        # Try direct path first
        direct_path = Path(file_path)
        if direct_path.exists():
            return direct_path
        
        # Try relative to target service
        relative_path = self.target_service_path / Path(file_path).name
        if relative_path.exists():
            return relative_path
        
        # Search in target service directory
        file_name = Path(file_path).name
        for found_file in self.target_service_path.rglob(file_name):
            if found_file.is_file():
                return found_file
        
        return None
    
    async def _get_code_context(
        self, 
        file_path: Path, 
        line_number: int,
        context_lines: int = 10
    ) -> Tuple[List[str], List[str]]:
        """Get code context around the error line"""
        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                content = await f.read()
                lines = content.split('\n')
                
                if line_number <= 0 or line_number > len(lines):
                    return [], []
                
                start = max(0, line_number - context_lines - 1)
                end = min(len(lines), line_number + context_lines)
                
                context_before = []
                context_after = []
                
                for i in range(start, line_number - 1):
                    context_before.append(f"{i + 1}: {lines[i]}")
                
                for i in range(line_number, end):
                    context_after.append(f"{i + 1}: {lines[i]}")
                
                return context_before, context_after
                
        except Exception as e:
            logger.error(f"Error reading source file: {e}")
            return [], []
    
    async def _analyze_root_cause(self, error_info: ErrorInfo) -> str:
        """Perform basic root cause analysis"""
        analysis_parts = []
        
        # Analyze error type
        if error_info.error_type == "TypeError":
            analysis_parts.append(
                "TypeError typically indicates an operation on an incompatible type. "
                "Check for undefined/null values or incorrect type usage."
            )
        elif error_info.error_type == "ReferenceError":
            analysis_parts.append(
                "ReferenceError indicates a reference to an undefined variable. "
                "Check variable declarations and scope."
            )
        elif error_info.error_type == "SyntaxError":
            analysis_parts.append(
                "SyntaxError indicates invalid code syntax. "
                "Check for missing brackets, quotes, or semicolons."
            )
        
        # Analyze message for common patterns
        message = error_info.message.lower()
        
        if "undefined" in message:
            analysis_parts.append(
                "The error involves an undefined value. "
                "Ensure all variables are properly initialized before use."
            )
        elif "null" in message:
            analysis_parts.append(
                "The error involves a null value. "
                "Add null checks before accessing properties."
            )
        elif "cannot read property" in message or "cannot read properties" in message:
            analysis_parts.append(
                "Attempting to access a property on undefined/null. "
                "Add defensive checks or use optional chaining (?.)."
            )
        elif "is not a function" in message:
            analysis_parts.append(
                "A non-function value is being called as a function. "
                "Check function definitions and imports."
            )
        elif "is not defined" in message:
            analysis_parts.append(
                "A variable or function is referenced but not defined. "
                "Check imports and variable declarations."
            )
        
        return " ".join(analysis_parts) if analysis_parts else "Unable to determine root cause automatically."
    
    async def get_full_file_content(self, file_path: Path) -> str:
        """Read full content of a source file"""
        try:
            async with aiofiles.open(file_path, 'r', encoding='utf-8') as f:
                return await f.read()
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            return ""
    
    async def get_related_code(self, error_info: ErrorInfo) -> dict:
        """Get code from all related files"""
        related_code = {}
        
        for file_path in error_info.related_files:
            resolved = await self._resolve_source_file(file_path)
            if resolved:
                content = await self.get_full_file_content(resolved)
                related_code[str(resolved)] = content
        
        return related_code
