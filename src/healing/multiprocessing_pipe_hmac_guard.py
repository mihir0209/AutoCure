import hashlib
import hmac
from typing import Tuple, Any

def verify_and_unpack_pipe_message(raw_payload: bytes, secret_token: bytes) -> Tuple[bool, bytes]:
    """
    Verifies HMAC-SHA256 signature on raw multiprocessing pipe IPC payloads before deserialization.
    """
    if len(raw_payload) < 32:
        return False, b""

    signature = raw_payload[:32]
    message_data = raw_payload[32:]
    expected_sig = hmac.new(secret_token, message_data, hashlib.sha256).digest()

    if hmac.compare_digest(signature, expected_sig):
        return True, message_data
    return False, b""
