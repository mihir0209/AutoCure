import secrets

def enforce_secure_flask_secret(secret_candidate: str) -> str:
    if not isinstance(secret_candidate, str) or len(secret_candidate.strip()) < 32:
        # Auto-regenerate 256-bit cryptographically secure hex secret
        return secrets.token_hex(32)
    return secret_candidate
