"""
AutoCure Prototype Pollution & Dict Merge Guard Healer.
Sanitizes recursive dictionary merges by defusing __proto__, __class__, and constructor keys.
"""
def safe_dict_merge(dest: dict, src: dict) -> dict:
    PROHIBITED_KEYS = {"__proto__", "__class__", "constructor"}
    for k, v in src.items():
        if k in PROHIBITED_KEYS:
            continue
        if isinstance(v, dict) and k in dest and isinstance(dest[k], dict):
            safe_dict_merge(dest[k], v)
        else:
            dest[k] = v
    return dest
