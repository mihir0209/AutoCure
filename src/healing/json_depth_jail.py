"""
AutoCure JSON Recursion Depth Stack Overflow Jail.
Limits maximum nesting depth to defend against deeply nested JSON DoS payloads.
"""
import json

def parse_json_with_depth_limit(json_str: str, max_depth: int = 50) -> any:
    data = json.loads(json_str)

    def check_depth(obj, current_depth: int = 0):
        if current_depth > max_depth:
            raise ValueError(f"JSON recursion depth {current_depth} exceeds maximum allowed depth of {max_depth}")
        if isinstance(obj, dict):
            for v in obj.values():
                check_depth(v, current_depth + 1)
        elif isinstance(obj, list):
            for item in obj:
                check_depth(item, current_depth + 1)

    check_depth(data, 0)
    return data
