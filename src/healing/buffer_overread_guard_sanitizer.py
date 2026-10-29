def safe_buffer_read_slice(buffer_bytes: bytes, requested_length: int, offset: int = 0) -> bytes:
    """
    Prevents Heartbleed-style memory overreading by clamping slice bounds strictly to available buffer length.
    """
    if not isinstance(buffer_bytes, (bytes, bytearray)):
        return b""
    actual_available = max(0, len(buffer_bytes) - offset)
    safe_length = min(max(0, requested_length), actual_available)
    return bytes(buffer_bytes[offset:offset + safe_length])
