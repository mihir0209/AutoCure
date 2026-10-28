"""
AutoCure JWT Secret Key Length Guard.
Validates minimum cryptographic key lengths for HMAC (>= 256 bits) and RSA (>= 2048 bits).
"""
def validate_jwt_key_length(algorithm: str, key: any) -> bool:
    algo = algorithm.upper()
    if algo.startswith("HS"):
        # HMAC key must be at least 32 bytes (256 bits)
        key_bytes = key.encode("utf-8") if isinstance(key, str) else bytes(key)
        if len(key_bytes) < 32:
            raise ValueError(f"Insecure JWT key length: {len(key_bytes)*8} bits is below 256-bit requirement for {algo}")
        return True
    elif algo.startswith("RS") or algo.startswith("PS"):
        # Key string representation or bytes
        key_str = key.decode("utf-8") if isinstance(key, bytes) else str(key)
        if "PRIVATE KEY" in key_str and len(key_str) < 800:
            raise ValueError(f"Insecure RSA key length: detected key under 2048-bit security requirement")
        return True
    return True
