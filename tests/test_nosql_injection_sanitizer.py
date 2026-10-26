import pytest
from healing.nosql_injection_sanitizer import (
    NoSQLInjectionSanitizer,
    sanitize_mongo_query_value,
)


def test_nosql_detects_dynamic_query_variable():
    code = """
from pymongo import MongoClient

db = MongoClient().mydb

def get_user(untrusted_query):
    return db.users.find_one(untrusted_query)
"""
    sanitizer = NoSQLInjectionSanitizer()
    findings = sanitizer.analyze(code)
    assert len(findings) == 1
    assert "find_one" in findings[0].vulnerable_call


def test_sanitize_mongo_query_value_blocks_operators():
    # Innocent user input
    assert sanitize_mongo_query_value("alice123") == "alice123"
    assert sanitize_mongo_query_value({"username": "bob"}) == {"username": "bob"}

    # Attacker tries to inject {"$gt": ""} to bypass password check
    with pytest.raises(ValueError, match="Prohibited NoSQL query operator: \$gt"):
        sanitize_mongo_query_value({"password": {"$gt": ""}})

    with pytest.raises(ValueError, match="Prohibited NoSQL query operator: \$regex"):
        sanitize_mongo_query_value({"token": {"$regex": "^admin"}})
