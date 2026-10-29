import math
import secrets
from typing import Tuple

def calculate_shannon_entropy(s: str) -> float:
    if not s:
        return 0.0
    freq = {}
    for c in s:
        freq[c] = freq.get(c, 0) + 1
    ent = 0.0
    n = len(s)
    for count in freq.values():
        p = count / n
        ent -= p * math.log2(p)
    return ent

def check_and_heal_jwt_secret(secret_key: str, min_entropy: float = 3.5, min_length: int = 32) -> Tuple[str, bool]:
    entropy = calculate_shannon_entropy(secret_key)
    # Check if key is weak (e.g. "secret", "password123", low length, or low entropy)
    is_weak = len(secret_key) < min_length or entropy < min_entropy or secret_key.lower() in ("secret", "password", "jwt_secret")
    if is_weak:
        # Auto-upgrade to high-entropy 256-bit URL-safe token
        new_secret = secrets.token_urlsafe(32)
        return new_secret, True
    return secret_key, False
