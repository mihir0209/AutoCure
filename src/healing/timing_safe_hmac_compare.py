import hmac

def timing_safe_verify(stored_hash: str, computed_hash: str) -> bool:
    if not isinstance(stored_hash, str) or not isinstance(computed_hash, str):
        return False
    return hmac.compare_digest(stored_hash.encode("utf-8"), computed_hash.encode("utf-8"))
