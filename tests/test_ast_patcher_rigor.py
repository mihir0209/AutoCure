"""
Adversarial QA Test Suite: AST Patcher Rigor, Fuzzing & Mutation Testing
========================================================================
Rigorous, high-coverage adversarial testing of AutoCure's Minimal-Diff AST Patcher.
Covers:
  1. Intentional syntax breaks (missing colons, unclosed delimiters, unclosed strings, etc.)
  2. IndexError defects across multiple syntactic structures (loads, stores, loops, expressions)
  3. KeyError defects across dictionaries, nested payloads, and membership guards
  4. Pseudo-random mutation & fuzzing engine verifying AST validity and compile invariants
  5. Multi-line, mangled, and adversarial traceback parsing
  6. Edge cases (bounds, empty files, idempotency, byte-level rollback)
"""

from __future__ import annotations

import ast
import difflib
import os
import random
import re
import sys
import tempfile
from pathlib import Path
from typing import List, Optional

import pytest

# Ensure src is in sys.path
SRC_DIR = str(Path(__file__).resolve().parent.parent / "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from healing.ast_patcher import ASTPatcher, ASTPatch, DefectPattern


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def patcher():
    """Default AST patcher instance."""
    return ASTPatcher()


@pytest.fixture
def mock_syntax_repo(tmp_path):
    """
    Mock repository containing multiple intentional syntax breaks.
    """
    repo = tmp_path / "syntax_defect_repo"
    repo.mkdir()

    # 1. Missing colon on function header
    file_func = repo / "bad_func.py"
    file_func.write_text(
        "def compute_average(values)\n"
        "    if not values:\n"
        "        return 0.0\n"
        "    return sum(values) / len(values)\n",
        encoding="utf-8",
    )

    # 2. Missing colon on if statement
    file_if = repo / "bad_if.py"
    file_if.write_text(
        "def check_limit(val: int) -> bool:\n"
        "    if val > 100\n"
        "        return True\n"
        "    return False\n",
        encoding="utf-8",
    )

    # 3. Missing colon on for loop
    file_for = repo / "bad_for.py"
    file_for.write_text(
        "def tally(items: list) -> int:\n"
        "    total = 0\n"
        "    for x in items\n"
        "        total += x\n"
        "    return total\n",
        encoding="utf-8",
    )

    # 4. Unclosed list bracket
    file_bracket = repo / "bad_bracket.py"
    file_bracket.write_text(
        "def get_whitelist():\n"
        "    allowed = [\"admin\", \"operator\", \"auditor\"\n"
        "    return allowed\n",
        encoding="utf-8",
    )

    # 5. Unclosed string literal
    file_string = repo / "bad_string.py"
    file_string.write_text(
        "def get_message():\n"
        "    msg = \"AutoCure Self-Healing Pipeline\n"
        "    return msg\n",
        encoding="utf-8",
    )

    # 6. Assignment in if statement condition (= instead of ==)
    file_assign = repo / "bad_assign.py"
    file_assign.write_text(
        "def check_mode(mode: str) -> bool:\n"
        "    if mode = \"active\":\n"
        "        return True\n"
        "    return False\n",
        encoding="utf-8",
    )

    return repo


@pytest.fixture
def mock_index_error_repo(tmp_path):
    """
    Mock repository containing various IndexError defect structures.
    """
    repo = tmp_path / "index_error_repo"
    repo.mkdir()

    # Out of bounds read in function
    file_read = repo / "buffer_reader.py"
    file_read.write_text(
        "def get_element(items: list, idx: int):\n"
        "    val = items[idx]\n"
        "    return val\n",
        encoding="utf-8",
    )

    # Assignment target IndexError
    file_store = repo / "buffer_writer.py"
    file_store.write_text(
        "def write_slot(slots: list, idx: int, value: str):\n"
        "    slots[idx] = value\n"
        "    return slots\n",
        encoding="utf-8",
    )

    # Complex multi-step expression with Subscript
    file_calc = repo / "data_processor.py"
    file_calc.write_text(
        "def compute_delta(series: list) -> float:\n"
        "    delta = series[10] - series[0]\n"
        "    return delta\n",
        encoding="utf-8",
    )

    return repo


@pytest.fixture
def mock_key_error_repo(tmp_path):
    """
    Mock repository containing KeyError defects across dict contexts.
    """
    repo = tmp_path / "key_error_repo"
    repo.mkdir()

    # Direct missing key lookup
    file_lookup = repo / "user_service.py"
    file_lookup.write_text(
        "def extract_user_id(session: dict) -> str:\n"
        "    uid = session[\"user_id\"]\n"
        "    return uid\n",
        encoding="utf-8",
    )

    # Nested dictionary missing key
    file_nested = repo / "config_loader.py"
    file_nested.write_text(
        "def load_timeout(cfg: dict) -> int:\n"
        "    settings = cfg[\"settings\"]\n"
        "    timeout = settings[\"timeout\"]\n"
        "    return timeout\n",
        encoding="utf-8",
    )

    return repo


# ============================================================================
# 1. Intentional Syntax Break Tests (Curing & AST Validation)
# ============================================================================

def test_syntax_break_missing_colon_on_def(mock_syntax_repo):
    """Verify missing colon on 'def' header is repaired and produces executable AST."""
    target_file = str(mock_syntax_repo / "bad_func.py")
    patcher = ASTPatcher(repo_path=str(mock_syntax_repo))

    # Precondition: file has invalid syntax
    with pytest.raises(SyntaxError):
        ast.parse(Path(target_file).read_text(encoding="utf-8"))

    patch = patcher.generate_patch(
        file_path="bad_func.py",
        line_number=1,
        defect_type="SyntaxError",
        error_message="expected ':'",
        repo_path=str(mock_syntax_repo),
    )

    assert patch is not None, "Patcher should successfully generate a syntax repair patch"
    assert patch.defect_type == DefectPattern.SYNTAX_ERROR
    assert "ast.SyntaxRepair" in patch.node_type

    # Strict AST syntax validation on the output code
    tree = ast.parse(patch.patched_code)
    assert tree is not None
    code_obj = compile(patch.patched_code, "<test_patch>", "exec")
    assert code_obj is not None

    # Apply patch to disk and execute function to prove defect is cured
    applied = patcher.apply_patch(patch, repo_path=str(mock_syntax_repo))
    assert applied is True

    namespace = {}
    exec(code_obj, namespace)
    compute_average = namespace["compute_average"]
    assert compute_average([10.0, 20.0, 30.0]) == 20.0
    assert compute_average([]) == 0.0


def test_syntax_break_missing_colon_on_if(mock_syntax_repo):
    """Verify missing colon on 'if' statement is healed and executes cleanly."""
    target_file = str(mock_syntax_repo / "bad_if.py")
    patcher = ASTPatcher(repo_path=str(mock_syntax_repo))

    with pytest.raises(SyntaxError):
        ast.parse(Path(target_file).read_text(encoding="utf-8"))

    patch = patcher.generate_patch(
        file_path="bad_if.py",
        line_number=2,
        defect_type="SyntaxError",
        error_message="expected ':'",
        repo_path=str(mock_syntax_repo),
    )

    assert patch is not None
    assert ast.parse(patch.patched_code)
    code_obj = compile(patch.patched_code, "<test_patch>", "exec")

    # Apply and test behavior
    patcher.apply_patch(patch, repo_path=str(mock_syntax_repo))
    ns = {}
    exec(code_obj, ns)
    check_limit = ns["check_limit"]
    assert check_limit(150) is True
    assert check_limit(50) is False


def test_syntax_break_missing_colon_on_for_loop(mock_syntax_repo):
    """Verify missing colon on 'for' loop header is healed."""
    patcher = ASTPatcher(repo_path=str(mock_syntax_repo))

    patch = patcher.generate_patch(
        file_path="bad_for.py",
        line_number=3,
        defect_type="SyntaxError",
        error_message="expected ':'",
        repo_path=str(mock_syntax_repo),
    )

    assert patch is not None
    assert ast.parse(patch.patched_code)
    ns = {}
    exec(compile(patch.patched_code, "<test>", "exec"), ns)
    assert ns["tally"]([1, 2, 3, 4]) == 10


def test_syntax_break_unclosed_delimiter(mock_syntax_repo):
    """Verify unclosed delimiter '[' is closed with valid syntax."""
    patcher = ASTPatcher(repo_path=str(mock_syntax_repo))

    patch = patcher.generate_patch(
        file_path="bad_bracket.py",
        line_number=2,
        defect_type="SyntaxError",
        error_message="'[' was never closed",
        repo_path=str(mock_syntax_repo),
    )

    assert patch is not None
    assert ast.parse(patch.patched_code)
    ns = {}
    exec(compile(patch.patched_code, "<test>", "exec"), ns)
    whitelist = ns["get_whitelist"]()
    assert "admin" in whitelist
    assert len(whitelist) == 3


def test_syntax_break_unclosed_string_quote(mock_syntax_repo):
    """Verify unterminated string literal is safely closed."""
    patcher = ASTPatcher(repo_path=str(mock_syntax_repo))

    patch = patcher.generate_patch(
        file_path="bad_string.py",
        line_number=2,
        defect_type="SyntaxError",
        error_message="unterminated string literal",
        repo_path=str(mock_syntax_repo),
    )

    assert patch is not None
    assert ast.parse(patch.patched_code)
    ns = {}
    exec(compile(patch.patched_code, "<test>", "exec"), ns)
    msg = ns["get_message"]()
    assert "AutoCure" in msg


def test_syntax_break_assignment_in_conditional(mock_syntax_repo):
    """Verify invalid '=' in if statement is replaced with '=='."""
    patcher = ASTPatcher(repo_path=str(mock_syntax_repo))

    patch = patcher.generate_patch(
        file_path="bad_assign.py",
        line_number=2,
        defect_type="SyntaxError",
        error_message="invalid syntax. Maybe you meant '=='?",
        repo_path=str(mock_syntax_repo),
    )

    assert patch is not None
    assert "==" in patch.patched_code
    assert ast.parse(patch.patched_code)
    ns = {}
    exec(compile(patch.patched_code, "<test>", "exec"), ns)
    check_mode = ns["check_mode"]
    assert check_mode("active") is True
    assert check_mode("inactive") is False


# ============================================================================
# 2. IndexError Defect Tests (Surgical Guards & Behavior)
# ============================================================================

def test_index_error_subscript_load_guard(mock_index_error_repo):
    """Verify IndexError on read is guarded with bounds check and returns None instead of crash."""
    patcher = ASTPatcher(repo_path=str(mock_index_error_repo))

    patch = patcher.generate_patch(
        file_path="buffer_reader.py",
        line_number=2,
        defect_type="IndexError",
        error_message="list index out of range",
        repo_path=str(mock_index_error_repo),
    )

    assert patch is not None
    assert patch.defect_type == DefectPattern.INDEX_ERROR
    assert "0 <=" in patch.patched_code
    assert "len(items)" in patch.patched_code
    assert ast.parse(patch.patched_code)

    # Apply and verify defect is cured
    patcher.apply_patch(patch, repo_path=str(mock_index_error_repo))
    ns = {}
    exec(compile(patch.patched_code, "<test>", "exec"), ns)
    get_element = ns["get_element"]

    # In-bounds works normally
    assert get_element(["first", "second"], 0) == "first"
    assert get_element(["first", "second"], 1) == "second"

    # Out-of-bounds no longer crashes with IndexError, returns None
    assert get_element(["first"], 5) is None
    assert get_element([], 0) is None


def test_index_error_subscript_store_guard(mock_index_error_repo):
    """Verify IndexError in assignment target (ast.Store) creates statement guard."""
    patcher = ASTPatcher(repo_path=str(mock_index_error_repo))

    patch = patcher.generate_patch(
        file_path="buffer_writer.py",
        line_number=2,
        defect_type="IndexError",
        error_message="list assignment index out of range",
        repo_path=str(mock_index_error_repo),
    )

    assert patch is not None
    # Must NOT generate invalid '(slots[idx] if ...) = value'
    assert "if 0 <= idx < len(slots):" in patch.patched_code
    assert ast.parse(patch.patched_code)

    ns = {}
    exec(compile(patch.patched_code, "<test>", "exec"), ns)
    write_slot = ns["write_slot"]

    # Valid index modifies slot
    assert write_slot(["a", "b"], 1, "updated") == ["a", "updated"]

    # Invalid index does not crash with IndexError
    assert write_slot(["a"], 99, "ignored") == ["a"]


def test_index_error_complex_expression(mock_index_error_repo):
    """Verify subscript within arithmetic binary operations is surgically guarded."""
    patcher = ASTPatcher(repo_path=str(mock_index_error_repo))

    patch = patcher.generate_patch(
        file_path="data_processor.py",
        line_number=2,
        defect_type="IndexError",
        error_message="list index out of range",
        repo_path=str(mock_index_error_repo),
    )

    assert patch is not None
    assert ast.parse(patch.patched_code)
    ns = {}
    exec(compile(patch.patched_code, "<test>", "exec"), ns)
    compute_delta = ns["compute_delta"]

    # If series has >= 11 elements
    series = [float(i) for i in range(12)]
    assert compute_delta(series) == 10.0


# ============================================================================
# 3. KeyError Defect Tests (Safe .get() & Membership Guards)
# ============================================================================

def test_key_error_converted_to_safe_get(mock_key_error_repo):
    """Verify KeyError is converted to safe dict.get(key, None)."""
    patcher = ASTPatcher(repo_path=str(mock_key_error_repo))

    patch = patcher.generate_patch(
        file_path="user_service.py",
        line_number=2,
        defect_type="KeyError",
        error_message="KeyError: 'user_id'",
        repo_path=str(mock_key_error_repo),
        use_membership_guard=False,
    )

    assert patch is not None
    assert patch.defect_type == DefectPattern.KEY_ERROR
    assert "session.get('user_id', None)" in patch.patched_code or 'session.get("user_id", None)' in patch.patched_code
    assert ast.parse(patch.patched_code)

    patcher.apply_patch(patch, repo_path=str(mock_key_error_repo))
    ns = {}
    exec(compile(patch.patched_code, "<test>", "exec"), ns)
    extract_user_id = ns["extract_user_id"]

    # Present key returns value
    assert extract_user_id({"user_id": "usr_9918"}) == "usr_9918"

    # Missing key does not raise KeyError, returns None
    assert extract_user_id({}) is None


def test_key_error_converted_to_membership_guard(mock_key_error_repo):
    """Verify KeyError with use_membership_guard=True produces membership guard."""
    patcher = ASTPatcher(repo_path=str(mock_key_error_repo))

    patch = patcher.generate_patch(
        file_path="user_service.py",
        line_number=2,
        defect_type="KeyError",
        error_message="KeyError: 'user_id'",
        repo_path=str(mock_key_error_repo),
        use_membership_guard=True,
    )

    assert patch is not None
    assert "'user_id' in session" in patch.patched_code or '"user_id" in session' in patch.patched_code
    assert ast.parse(patch.patched_code)

    ns = {}
    exec(compile(patch.patched_code, "<test>", "exec"), ns)
    extract_user_id = ns["extract_user_id"]
    assert extract_user_id({}) is None
    assert extract_user_id({"user_id": "test_id"}) == "test_id"


def test_key_error_nested_dict(mock_key_error_repo):
    """Verify targeted KeyError resolution in nested structure."""
    patcher = ASTPatcher(repo_path=str(mock_key_error_repo))

    # Target line 3: timeout = settings["timeout"]
    patch = patcher.generate_patch(
        file_path="config_loader.py",
        line_number=3,
        defect_type="KeyError",
        error_message="KeyError: 'timeout'",
        repo_path=str(mock_key_error_repo),
    )

    assert patch is not None
    assert "settings.get('timeout', None)" in patch.patched_code or 'settings.get("timeout", None)' in patch.patched_code
    assert ast.parse(patch.patched_code)

    ns = {}
    exec(compile(patch.patched_code, "<test>", "exec"), ns)
    load_timeout = ns["load_timeout"]
    assert load_timeout({"settings": {}}) is None
    assert load_timeout({"settings": {"timeout": 60}}) == 60


# ============================================================================
# 4. Fuzzing & Mutation Testing Suite
# ============================================================================

BASELINE_SOURCE_CORPUS = [
    """
def calculate_ratio(dividend: float, divisor: float) -> float:
    ratio = dividend / divisor
    return ratio
""",
    """
def fetch_user_record(users: list, user_id: int):
    target = users[user_id]
    return target
""",
    """
def get_service_setting(options: dict, key: str):
    val = options[key]
    return val
""",
    """
def evaluate_status(status_code: int) -> str:
    if status_code == 200:
        return "OK"
    return "ERROR"
""",
    """
def sum_matrix(matrix: list) -> int:
    total = 0
    for row in matrix:
        for val in row:
            total += val
    return total
""",
]


def test_fuzzing_random_mutations_and_ast_invariants(tmp_path):
    """
    Adversarial Mutation Fuzzer:
    Applies synthetic mutations (syntax breaks, out-of-bound indexes, missing keys,
    corrupted conditionals) across a corpus of valid Python code.
    Asserts that:
      1. Every generated patch passes ast.parse() and compile().
      2. No patch introduces syntax regressions.
      3. Unified diffs are non-empty and well-formed.
    """
    rng = random.Random(1337)  # Deterministic seed for reproducible adversarial runs

    repo_dir = tmp_path / "fuzz_repo"
    repo_dir.mkdir()

    total_mutations = 30
    patches_generated = 0

    for i in range(total_mutations):
        base_code = rng.choice(BASELINE_SOURCE_CORPUS)
        file_name = f"fuzz_module_{i}.py"
        file_path = repo_dir / file_name

        mutation_type = rng.choice([
            "strip_colon",
            "unclosed_paren",
            "unclosed_bracket",
            "unclosed_quote",
            "assign_in_cond",
            "index_error",
            "key_error",
            "zero_division",
        ])

        mutated_code = base_code
        target_line = 2
        defect_type = "SyntaxError"
        err_msg = ""

        if mutation_type == "strip_colon":
            # Remove colon from first 'def' or 'if' or 'for'
            mutated_code = re.sub(r":\s*$", "", base_code, count=1, flags=re.MULTILINE)
            defect_type = "SyntaxError"
            err_msg = "expected ':'"
            target_line = 2

        elif mutation_type == "unclosed_paren":
            mutated_code = base_code.replace(")", "", 1)
            defect_type = "SyntaxError"
            err_msg = "unclosed parenthesis"
            target_line = 2

        elif mutation_type == "unclosed_bracket":
            mutated_code = base_code.replace("]", "", 1)
            defect_type = "SyntaxError"
            err_msg = "'[' was never closed"
            target_line = 2

        elif mutation_type == "unclosed_quote":
            mutated_code = base_code.replace('"OK"', '"OK', 1)
            defect_type = "SyntaxError"
            err_msg = "unterminated string literal"
            target_line = 3

        elif mutation_type == "assign_in_cond":
            mutated_code = base_code.replace("==", "=", 1)
            defect_type = "SyntaxError"
            err_msg = "invalid syntax. Maybe you meant '=='?"
            target_line = 3

        elif mutation_type == "index_error":
            defect_type = "IndexError"
            err_msg = "list index out of range"
            target_line = 3

        elif mutation_type == "key_error":
            defect_type = "KeyError"
            err_msg = "KeyError: 'target_key'"
            target_line = 3

        elif mutation_type == "zero_division":
            defect_type = "ZeroDivisionError"
            err_msg = "division by zero"
            target_line = 3

        file_path.write_text(mutated_code, encoding="utf-8")

        patcher = ASTPatcher(repo_path=str(repo_dir))
        patch = patcher.generate_patch(
            file_path=file_name,
            line_number=target_line,
            defect_type=defect_type,
            error_message=err_msg,
            repo_path=str(repo_dir),
        )

        if patch is not None:
            patches_generated += 1

            # INVARIANT 1: Patched code must be valid syntax
            parsed = ast.parse(patch.patched_code)
            assert parsed is not None, f"Patch {i} failed ast.parse"

            # INVARIANT 2: Patched code must compile cleanly
            compiled = compile(patch.patched_code, f"<fuzz_{i}>", "exec")
            assert compiled is not None, f"Patch {i} failed compilation"

            # INVARIANT 3: Unified diff must be valid
            assert "--- a/" in patch.diff or "+++ b/" in patch.diff
            assert len(patch.diff) > 0

            # INVARIANT 4: File application and rollback cycle must be idempotent
            applied = patcher.apply_patch(patch, repo_path=str(repo_dir))
            assert applied is True
            assert Path(file_path).read_text(encoding="utf-8") == patch.patched_code

            rolled_back = patcher.rollback_patch(patch, repo_path=str(repo_dir))
            assert rolled_back is True
            assert Path(file_path).read_text(encoding="utf-8") == mutated_code

    assert patches_generated >= 15, f"Expected at least 15 patches generated, got {patches_generated}"


# ============================================================================
# 5. Adversarial Traceback Parsing & Edge Cases
# ============================================================================

def test_parse_traceback_pytest_and_standard_formats():
    """Verify traceback parser handles varied stack formats."""
    # Standard Python traceback
    tb_std = """
Traceback (most recent call last):
  File "src/core/math_service.py", line 42, in calculate_average
    result = total / count
ZeroDivisionError: division by zero
"""
    parsed = ASTPatcher.parse_traceback(tb_std)
    assert parsed is not None
    f, line, defect, msg = parsed
    assert f == "src/core/math_service.py"
    assert line == 42
    assert defect == "ZeroDivisionError"
    assert "division by zero" in msg

    # SyntaxError traceback format
    tb_syntax = """
  File "gateway/router.py", line 18
    def route_request(req)
                          ^
SyntaxError: expected ':'
"""
    parsed_syntax = ASTPatcher.parse_traceback(tb_syntax)
    assert parsed_syntax is not None
    sf, sline, sdefect, smsg = parsed_syntax
    assert sf == "gateway/router.py"
    assert sline == 18
    assert sdefect == "SyntaxError"

    # Multi-hop traceback selects the innermost frame matching repo
    with tempfile.TemporaryDirectory() as td:
        service_file = Path(td) / "app.py"
        service_file.write_text("x = 1\n", encoding="utf-8")

        tb_multihop = f"""
Traceback (most recent call last):
  File "/usr/lib/python3.11/asyncio/runners.py", line 118, in run
    return self._loop.run_until_complete(task)
  File "/usr/lib/python3.11/asyncio/base_events.py", line 654, in run_until_complete
    return future.result()
  File "{service_file}", line 1, in main
    val = data[0]
IndexError: list index out of range
"""
        parsed_multi = ASTPatcher.parse_traceback(tb_multihop, repo_path=td)
        assert parsed_multi is not None
        mf, mline, mdefect, _ = parsed_multi
        assert mf == "app.py"
        assert mline == 1
        assert mdefect == "IndexError"


def test_patcher_edge_cases_nonexistent_and_out_of_bounds(tmp_path):
    """Verify patcher rejects invalid files, out of bounds lines, and empty files gracefully."""
    patcher = ASTPatcher(repo_path=str(tmp_path))

    # 1. Nonexistent file
    patch_none = patcher.generate_patch(
        file_path="nonexistent_module.py",
        line_number=10,
        defect_type="IndexError",
        repo_path=str(tmp_path),
    )
    assert patch_none is None

    # 2. Line number 0 or exceeding line count
    valid_file = tmp_path / "valid.py"
    valid_file.write_text("print('hello')\n", encoding="utf-8")

    patch_out_of_bounds = patcher.generate_patch(
        file_path="valid.py",
        line_number=9999,
        defect_type="IndexError",
        repo_path=str(tmp_path),
    )
    assert patch_out_of_bounds is None

    patch_zero = patcher.generate_patch(
        file_path="valid.py",
        line_number=0,
        defect_type="IndexError",
        repo_path=str(tmp_path),
    )
    assert patch_zero is None

    # 3. Empty file
    empty_file = tmp_path / "empty.py"
    empty_file.write_text("", encoding="utf-8")

    patch_empty = patcher.generate_patch(
        file_path="empty.py",
        line_number=1,
        defect_type="IndexError",
        repo_path=str(tmp_path),
    )
    assert patch_empty is None


def test_patch_to_dict_schema():
    """Verify ASTPatch.to_dict serialization schema for dashboard/CI ingestion."""
    patch = ASTPatch(
        file_path="services/billing.py",
        line_number=55,
        defect_type="KeyError",
        original_code="val = d['k']\n",
        patched_code="val = d.get('k', None)\n",
        diff="--- a\n+++ b\n",
        node_type="ast.Subscript",
        explanation="Convert to dict.get",
        original_line="val = d['k']",
        patched_line="val = d.get('k', None)",
        confidence=0.98,
        metadata={"custom": "field"},
    )
    d = patch.to_dict()
    assert d["file_path"] == "services/billing.py"
    assert d["line_number"] == 55
    assert d["defect_type"] == "KeyError"
    assert d["node_type"] == "ast.Subscript"
    assert d["confidence"] == 0.98
    assert d["metadata"]["custom"] == "field"
