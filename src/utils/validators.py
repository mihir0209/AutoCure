"""
Validation utilities for AutoCure
- Configuration validation (secrets, tokens)
- Syntax validation before code application
- Input sanitization
"""

import ast
import os
import re
from pathlib import Path
from typing import Optional, Tuple

from utils.logger import setup_colored_logger

logger = setup_colored_logger("validators")


# ════════════════════════════════════════════════════════════════
#  Configuration Validation
# ════════════════════════════════════════════════════════════════

INSECURE_DEFAULTS = {
    "change-this-jwt-secret-in-production",
    "change-this-encryption-key-in-production",
    "changeme",
    "secret",
    "password",
    "your_secret_here",
    "your_token_here",
    "your_key_here",
}


def validate_secret(
    secret: str, min_length: int = 32, name: str = "secret"
) -> Tuple[bool, str]:
    """
    Validate a secret/token meets security requirements.
    
    Returns: (is_valid, error_message)
    """
    if not secret or not secret.strip():
        return False, f"{name} is empty"
    
    secret_lower = secret.lower().strip()
    
    # Check against known insecure defaults
    if secret_lower in INSECURE_DEFAULTS:
        return False, f"{name} is using an insecure default value"
    
    # Check for placeholder patterns
    placeholder_patterns = [
        r"^change.*production",
        r"your.*here",
        r"^(secret|password|token|key)$",
        r"^(test|demo|sample)",
    ]
    for pattern in placeholder_patterns:
        if re.match(pattern, secret_lower):
            return False, f"{name} appears to be a placeholder value"
    
    # Check minimum length
    if len(secret) < min_length:
        return False, f"{name} must be at least {min_length} characters (got {len(secret)})"
    
    # Check entropy (basic check - should have mix of character types)
    has_lower = any(c.islower() for c in secret)
    has_upper = any(c.isupper() for c in secret)
    has_digit = any(c.isdigit() for c in secret)
    
    if not (has_lower or has_upper or has_digit):
        return False, f"{name} should contain a mix of letters and numbers"
    
    return True, ""


def validate_production_config(config) -> list[str]:
    """
    Validate configuration for production deployment.
    
    Returns list of warnings/errors.
    """
    warnings = []
    
    # Check JWT secret
    is_valid, msg = validate_secret(
        config.server.jwt_secret,
        min_length=32,
        name="JWT secret"
    )
    if not is_valid:
        warnings.append(f"🔴 CRITICAL: {msg}")
    
    # Check database encryption key
    is_valid, msg = validate_secret(
        config.database.encryption_key,
        min_length=32,
        name="Database encryption key"
    )
    if not is_valid:
        warnings.append(f"🔴 CRITICAL: {msg}")
    
    # Check CORS origins
    if "*" in config.server.cors_origins:
        warnings.append(
            "🟡 WARNING: CORS allows all origins (*) — restrict in production"
        )
    
    # Check default admin credentials (if auth system uses them)
    # This would need to check the actual auth DB, skipping for now
    
    # Check AI provider credentials
    if config.ai.provider == "groq" and not config.ai.groq_api_key:
        warnings.append("🟡 WARNING: Groq API key not configured")
    elif config.ai.provider == "cerebras" and not config.ai.cerebras_api_key:
        warnings.append("🟡 WARNING: Cerebras API key not configured")
    elif config.ai.provider == "azure":
        if not config.ai.azure_openai_api_key:
            warnings.append("🟡 WARNING: Azure OpenAI API key not configured")
        if not config.ai.azure_openai_endpoint:
            warnings.append("🟡 WARNING: Azure OpenAI endpoint not configured")
    
    return warnings


# ════════════════════════════════════════════════════════════════
#  Syntax Validation (before applying code fixes)
# ════════════════════════════════════════════════════════════════

def validate_python_syntax(code: str) -> Tuple[bool, str]:
    """
    Validate Python code syntax.
    
    Returns: (is_valid, error_message)
    """
    if not code or not code.strip():
        return False, "Empty code"
    
    try:
        ast.parse(code)
        return True, ""
    except SyntaxError as e:
        return False, f"Syntax error at line {e.lineno}: {e.msg}"
    except Exception as e:
        return False, f"Parse error: {str(e)}"


def validate_javascript_syntax(code: str) -> Tuple[bool, str]:
    """
    Basic JavaScript syntax validation.
    
    Note: This is a basic check. For production, consider using a
    proper JS parser like esprima or running node with --check.
    """
    if not code or not code.strip():
        return False, "Empty code"
    
    # Basic bracket/brace matching
    brackets = {"(": ")", "[": "]", "{": "}"}
    stack = []
    in_string = False
    string_char = None
    escape_next = False
    
    for i, char in enumerate(code):
        if escape_next:
            escape_next = False
            continue
        
        if char == "\\":
            escape_next = True
            continue
        
        if char in ('"', "'", "`") and not in_string:
            in_string = True
            string_char = char
            continue
        
        if in_string and char == string_char:
            in_string = False
            string_char = None
            continue
        
        if in_string:
            continue
        
        if char in brackets:
            stack.append(char)
        elif char in brackets.values():
            if not stack:
                return False, f"Unmatched closing '{char}' at position {i}"
            opener = stack.pop()
            if brackets[opener] != char:
                return False, f"Mismatched brackets: '{opener}' vs '{char}' at position {i}"
    
    if stack:
        return False, f"Unclosed bracket: '{stack[-1]}'"
    
    if in_string:
        return False, f"Unclosed string (started with {string_char})"
    
    return True, ""


def validate_code_syntax(code: str, language: str) -> Tuple[bool, str]:
    """
    Validate code syntax based on language.
    
    Returns: (is_valid, error_message)
    """
    if not code or not code.strip():
        return False, "Empty code"
    
    language_lower = language.lower()
    
    if language_lower in ("python", "py"):
        return validate_python_syntax(code)
    elif language_lower in ("javascript", "js", "typescript", "ts"):
        return validate_javascript_syntax(code)
    else:
        # For unsupported languages, do basic sanity checks
        # Check for balanced braces/brackets
        if language_lower in ("java", "c", "cpp", "go", "rust", "csharp"):
            return validate_javascript_syntax(code)  # Similar syntax rules
        
        # Default: assume valid (better than blocking legitimate fixes)
        return True, f"Syntax validation not implemented for {language}"


# ════════════════════════════════════════════════════════════════
#  Path Validation (prevent traversal attacks)
# ════════════════════════════════════════════════════════════════

def validate_repo_path(file_path: str, repo_root: str) -> Tuple[bool, str]:
    """
    Validate that a file path is within the repository root.
    
    Returns: (is_valid, error_message)
    """
    try:
        repo_root_resolved = Path(repo_root).resolve()
        file_resolved = (repo_root_resolved / file_path).resolve()
        
        # Check that file is within repo
        file_resolved.relative_to(repo_root_resolved)
        
        return True, ""
    except ValueError:
        return False, f"Path traversal detected: {file_path} is outside repository"
    except Exception as e:
        return False, f"Invalid path: {str(e)}"


# ════════════════════════════════════════════════════════════════
#  Input Sanitization
# ════════════════════════════════════════════════════════════════

def sanitize_repo_url(url: str) -> str:
    """Sanitize a repository URL."""
    # Remove any embedded credentials
    url = re.sub(r'://[^@]+@', '://', url)
    # Ensure HTTPS
    if url.startswith("http://"):
        url = url.replace("http://", "https://", 1)
    return url.strip()


def is_safe_filename(filename: str) -> bool:
    """Check if a filename is safe (no path traversal)."""
    return ".." not in filename and "/" not in filename and "\\" not in filename
