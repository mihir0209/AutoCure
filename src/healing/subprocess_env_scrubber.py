DANGEROUS_ENV_VARS = {
    "LD_PRELOAD",
    "LD_LIBRARY_PATH",
    "PYTHONPATH",
    "PYTHONHOME",
    "NODE_OPTIONS",
    "RUBYLIB",
    "PERL5LIB",
}

def scrub_subprocess_env(env_dict: dict) -> dict:
    if not isinstance(env_dict, dict):
        return {}
    clean_env = env_dict.copy()
    for var in DANGEROUS_ENV_VARS:
        clean_env.pop(var, None)
    return clean_env
