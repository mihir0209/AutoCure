import re

def scrub_sensitive_environ_strings(log_or_error_text: str) -> str:
    """
    Scrubs sensitive credential variables in dumps of os.environ or logs.
    """
    if not isinstance(log_or_error_text, str):
        return ""
    # Scrub API keys, tokens, secret keys, passwords
    pattern = r"(?i)(api[_-]?key|token|secret|password|auth|private[_-]?key)\s*[:=]\s*['\"]?([A-Za-z0-9_\-\.\$\+\/]{8,})['\"]?"
    scrubbed = re.sub(pattern, r"\1=[REDACTED_SECRET]", log_or_error_text)
    return scrubbed
