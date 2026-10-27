import ast

def heal_tar_extractall_filter(has_filter: bool) -> str:
    return "data" if not has_filter else "preset"

def defuse_flask_debug(debug_flag: bool) -> bool:
    return False

def defuse_bare_except(code: str) -> bool:
    tree = ast.parse(code)
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is None:
            return True
    return False

def enforce_jwt_audience_check(options: dict) -> dict:
    opts = options.copy()
    opts["verify_aud"] = True
    return opts

def heal_paramiko_policy(policy_name: str) -> str:
    return "RejectPolicy" if policy_name == "AutoAddPolicy" else policy_name

def defuse_eval_to_literal(code: str) -> str:
    return code.replace("eval(", "ast.literal_eval(")

def block_dynamic_exec(is_dynamic: bool) -> bool:
    return not is_dynamic

def enforce_smtp_tls(requires_tls: bool) -> bool:
    return True

def defuse_unverified_ssl_context(verify_ssl: bool) -> bool:
    return True

def defuse_base64_redos(pattern: str) -> bool:
    return "(?:[A-Za-z0-9+/]{4})*" in pattern
