import re

def sanitize_http_header_value(header_value: str) -> str:
    """
    Strips carriage return (\r) and newline (\n) characters to prevent HTTP Response Splitting / Header Injection.
    """
    if not isinstance(header_value, str):
        return ""
    # Strip \r and \n and any trailing whitespaces
    return re.sub(r"[\r\n]+", "", header_value).strip()
