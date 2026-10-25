"""Tests for SQL Injection Vulnerability Heuristic & Parameterized Query Synthesizer."""

import ast
import pytest
from healing.sql_injection_synthesizer import (
    SQLInjectionSynthesizer,
    synthesize_parameterized_queries,
)


def test_detects_f_string_sql_injection():
    code = """
def fetch_user(cursor, user_id):
    cursor.execute(f"SELECT * FROM users WHERE id = {user_id}")
"""
    engine = SQLInjectionSynthesizer()
    findings = engine.analyze(code)
    assert len(findings) == 1
    assert findings[0].vulnerability_type == "f-string"
    assert findings[0].recommended_query == "SELECT * FROM users WHERE id = %s"
    assert findings[0].extracted_params == ["user_id"]

    healed, _ = engine.synthesize(code)
    assert "cursor.execute('SELECT * FROM users WHERE id = %s', (user_id,))" in healed


def test_detects_modulo_and_format_call():
    code = """
def update_balance(db, amount, account_id):
    db.execute("UPDATE accounts SET balance = %s WHERE id = %s" % (amount, account_id))
    db.execute("SELECT name FROM accounts WHERE id = {}".format(account_id))
"""
    healed, findings = synthesize_parameterized_queries(code)
    assert len(findings) == 2
    assert findings[0].vulnerability_type == "percent_format"
    assert findings[1].vulnerability_type == "str_format"

    assert "db.execute('UPDATE accounts SET balance = %s WHERE id = %s', (amount, account_id))" in healed
    assert "db.execute('SELECT name FROM accounts WHERE id = %s', (account_id,))" in healed


def test_detects_string_concatenation_sql():
    code = """
def find_by_name(cursor, name):
    cursor.execute("SELECT * FROM clients WHERE name = " + name)
"""
    healed, findings = synthesize_parameterized_queries(code)
    assert len(findings) == 1
    assert findings[0].vulnerability_type == "concat"
    assert "cursor.execute('SELECT * FROM clients WHERE name = %s', (name,))" in healed


def test_ignores_already_safe_parameterized_queries():
    code = """
def safe_query(cursor, user_id):
    cursor.execute("SELECT * FROM users WHERE id = %s", (user_id,))
    cursor.execute("SELECT count(*) FROM users")
"""
    healed, findings = synthesize_parameterized_queries(code)
    assert len(findings) == 0
    assert ast.dump(ast.parse(healed)) == ast.dump(ast.parse(code))
