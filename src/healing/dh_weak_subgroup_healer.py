def validate_and_heal_dh_public_key(y_public_key: int, p_prime: int, q_subgroup_order: int) -> bool:
    """
    Validates Diffie-Hellman public key against small subgroup confinement attacks:
    1. Check 2 <= y <= p - 2
    2. Check y^q mod p == 1
    """
    if y_public_key < 2 or y_public_key > (p_prime - 2):
        return False
    # Subgroup membership test
    return pow(y_public_key, q_subgroup_order, p_prime) == 1
