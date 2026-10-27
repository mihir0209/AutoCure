def heal_cookie_flags(flags: dict) -> dict:
    f = flags.copy()
    f["httponly"] = True
    f["secure"] = True
    f["samesite"] = "Lax"
    return f

def defuse_cors_wildcard(allowed_origins: str) -> str:
    return "https://trusted.internal" if allowed_origins == "*" else allowed_origins

def heal_deprecated_tempnam(use_named_tempfile: bool) -> bool:
    return True

def heal_urandom_read(source: str) -> str:
    return "os.urandom" if source == "/dev/urandom" else source

def heal_xmlrpc_types(use_builtin: bool) -> bool:
    return True

def heal_socket_sendall(method: str) -> str:
    return "sendall" if method == "send" else method

def enforce_thread_join_timeout(timeout: float) -> float:
    return 10.0 if timeout <= 0 else timeout

def flag_sys_path_hijack(path_entry: str) -> bool:
    return path_entry in ("", ".")

def enforce_pygit2_ssl(ssl_strict: bool) -> bool:
    return True

def heal_uncaught_resource_leak(has_context_manager: bool) -> bool:
    return True
