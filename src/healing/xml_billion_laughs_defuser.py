import re

def defuse_xml_billion_laughs_entities(xml_content: str) -> str:
    """
    Strips recursive internal general ENTITY declarations causing exponential entity expansion (Billion Laughs / XML bomb).
    """
    if not isinstance(xml_content, str):
        return ""
    # Strip <!ENTITY ...> declarations
    clean_xml = re.sub(r"<!ENTITY\s+[^>]+>", "", xml_content, flags=re.IGNORECASE)
    # Strip inline DTD doctype if entities existed
    if "<!DOCTYPE" in clean_xml and "SYSTEM" not in clean_xml:
        clean_xml = re.sub(r"<!DOCTYPE\s+[^>\[]+\[\s*\]>", "", clean_xml)
    return clean_xml
