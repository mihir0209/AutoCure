import pickletools
import io

DANGEROUS_OPCODES = {"GLOBAL", "REDUCE", "BUILD", "INST", "OBJ", "STACK_GLOBAL"}

def verify_safe_pickle_stream(pickle_bytes: bytes) -> bool:
    try:
        opcodes = set()
        for opcode, arg, pos in pickletools.genops(io.BytesIO(pickle_bytes)):
            opcodes.add(opcode.name)
            if opcode.name in DANGEROUS_OPCODES:
                raise PermissionError(f"Insecure pickle deserialization blocked: dangerous opcode '{opcode.name}' detected")
        return True
    except Exception as e:
        if isinstance(e, PermissionError):
            raise
        raise ValueError(f"Corrupt or invalid pickle payload: {e}")
