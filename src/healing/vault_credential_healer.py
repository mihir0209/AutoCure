import re

AWS_KEY_PATTERN = re.compile(r"""(["'])(AKIA[0-9A-Z]{16})\1""")

def heal_hardcoded_aws_credentials(code: str, env_var_name: str = "AWS_ACCESS_KEY_ID") -> str:
    # Replaces hardcoded AWS key literal with os.environ.get(env_var_name)
    def replacer(match):
        return f'os.environ.get("{env_var_name}")'
    return AWS_KEY_PATTERN.sub(replacer, code)
