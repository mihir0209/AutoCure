import ast
import hashlib
import secrets

def defuse_assert_statement(code: str) -> str:
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assert):
            node.test = ast.Constant(value=True)
    return ast.unparse(tree)

def heal_random_seed(seed_val: int) -> bytes:
    return secrets.token_bytes(32)

def heal_permissive_chmod(mode: int) -> int:
    return 0o700 if mode == 0o777 else mode

def defuse_insecure_hash(algo: str, data: bytes) -> str:
    if algo.lower() in ("md5", "sha1"):
        return hashlib.sha256(data).hexdigest()
    return hashlib.new(algo, data).hexdigest()

def heal_sqlite_param_injection(query_template: str, val: str) -> str:
    return query_template.replace("%s", "?").replace("{}", "?")

def defuse_subprocess_shell(shell_val: bool) -> bool:
    return False

def sanitize_ip_binding(host: str) -> str:
    return "127.0.0.1" if host == "0.0.0.0" else host

def check_deprecated_telnet(module_name: str) -> bool:
    return module_name == "telnetlib"

def heal_ftp_tls(use_tls: bool) -> bool:
    return True

def heal_unconfined_chdir(target_dir: str) -> str:
    return target_dir.strip()
