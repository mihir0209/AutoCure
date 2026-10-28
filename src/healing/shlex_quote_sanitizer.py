import shlex

def sanitize_shell_command_args(args: list) -> str:
    return " ".join(shlex.quote(str(arg)) for arg in args)
