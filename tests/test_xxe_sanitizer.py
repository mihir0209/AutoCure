import pytest
from healing.xxe_sanitizer import XXESanitizer, sanitize_xxe, XXEFinding


def test_xxe_detects_elementtree_fromstring():
    code = """
import xml.etree.ElementTree as ET

def parse_xml_payload(user_xml):
    root = ET.fromstring(user_xml)
    return root.tag
"""
    sanitizer = XXESanitizer()
    findings = sanitizer.analyze(code)
    assert len(findings) == 1
    assert "ET.fromstring" in findings[0].vulnerable_parser
    assert "XXE" in findings[0].vulnerability_reason


def test_xxe_detects_minidom_parse():
    code = """
from xml.dom import minidom

def load_config(xml_path):
    dom = minidom.parse(xml_path)
    return dom
"""
    sanitizer = XXESanitizer()
    findings = sanitizer.analyze(code)
    assert len(findings) == 1
    assert "minidom.parse" in findings[0].vulnerable_parser


def test_xxe_synthesizes_defusedxml_elementtree():
    bad_code = """
import xml.etree.ElementTree as ET

def parse_invoice(xml_str):
    return ET.fromstring(xml_str)
"""
    healed, findings = sanitize_xxe(bad_code)
    assert len(findings) == 1
    assert "defusedxml.ElementTree" in healed
    assert "xml.etree.ElementTree" not in healed
    compile(healed, "<test>", "exec")


def test_xxe_synthesizes_defusedxml_minidom():
    bad_code = """
import xml.dom.minidom as minidom

def parse_doc(stream):
    return minidom.parse(stream)
"""
    healed, findings = sanitize_xxe(bad_code)
    assert len(findings) == 1
    assert "defusedxml.minidom" in healed
    compile(healed, "<test>", "exec")


def test_xxe_clean_code_unchanged():
    clean_code = """
import json

def parse_json(payload):
    return json.loads(payload)
"""
    sanitizer = XXESanitizer()
    findings = sanitizer.analyze(clean_code)
    assert len(findings) == 0

    healed, findings = sanitize_xxe(clean_code)
    assert len(findings) == 0
    assert healed == clean_code
