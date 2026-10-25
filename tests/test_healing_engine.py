"""
Unit and Integration Tests for AutoCure Healing Module
======================================================
Tests:
  - Minimal-Diff AST Patch Generator (src/healing/ast_patcher.py):
      * IndexError bounds check guard
      * KeyError dict.get / membership test
      * AttributeError / NoneType null-coalescing guard
      * ZeroDivisionError non-zero divisor guard
      * ast.parse() validation on all nodes
  - Regression Verifier & Auto-Rollback (src/healing/verifier.py):
      * pytest execution on patched code
      * Automatic rollback upon regression/failure
      * Regression warning recording
  - Standalone CLI Entrypoint:
      * 'autocure heal --check --repo <path>'
"""

import ast
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path
import pytest

# Ensure src is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from healing.ast_patcher import ASTPatcher, ASTPatch, DefectPattern
from healing.verifier import RegressionVerifier, VerificationResult
from healing.cli import main as cli_main


# ============================================================================
# 1. AST Patcher - IndexError (Array Bounds Check Guard)
# ============================================================================

def test_ast_patcher_index_error_bounds_check(tmp_path):
    """Verify IndexError generates a minimal-diff array bounds check guard."""
    code = '''def get_nth_element(items, idx):
    element = items[idx]
    return element
'''
    src_file = tmp_path / "index_demo.py"
    src_file.write_text(code)

    patcher = ASTPatcher(repo_path=str(tmp_path))
    patch = patcher.generate_patch(
        file_path="index_demo.py",
        line_number=2,
        defect_type=DefectPattern.INDEX_ERROR,
        error_message="list index out of range",
    )

    assert patch is not None
    assert patch.defect_type == "IndexError"
    assert patch.line_number == 2
    assert "0 <= idx < len(items)" in patch.patched_line
    assert "items[idx]" in patch.patched_line

    # Verify every generated node parses with ast.parse()
    parsed_tree = ast.parse(patch.patched_code)
    assert parsed_tree is not None
    assert "-    element = items[idx]" in patch.diff
    assert "+    element = (items[idx] if 0 <= idx < len(items) else None)" in patch.diff


def test_ast_patcher_index_error_traceback(tmp_path):
    """Verify IndexError patch generation directly from traceback text."""
    code = '''def pick_first(sequence):
    return sequence[0]
'''
    src_file = tmp_path / "picker.py"
    src_file.write_text(code)

    traceback_str = f"""Traceback (most recent call last):
  File "{src_file}", line 2, in pick_first
    return sequence[0]
IndexError: list index out of range"""

    patcher = ASTPatcher(repo_path=str(tmp_path))
    patch = patcher.generate_patch_from_traceback(traceback_str)

    assert patch is not None
    assert patch.line_number == 2
    assert "0 <= 0 < len(sequence)" in patch.patched_code
    # Validate with ast.parse()
    ast.parse(patch.patched_code)


# ============================================================================
# 2. AST Patcher - KeyError (dict.get & Membership Guard)
# ============================================================================

def test_ast_patcher_key_error_dict_get(tmp_path):
    """Verify KeyError converts dict[key] to dict.get(key, None)."""
    code = '''def lookup_header(headers, header_name):
    val = headers[header_name]
    return val
'''
    src_file = tmp_path / "headers.py"
    src_file.write_text(code)

    patcher = ASTPatcher(repo_path=str(tmp_path))
    patch = patcher.generate_patch(
        file_path="headers.py",
        line_number=2,
        defect_type=DefectPattern.KEY_ERROR,
        error_message="KeyError: 'authorization'",
    )

    assert patch is not None
    assert "headers.get(header_name, None)" in patch.patched_line
    # Validate with ast.parse()
    ast.parse(patch.patched_code)
    assert "-    val = headers[header_name]" in patch.diff
    assert "+    val = headers.get(header_name, None)" in patch.diff


def test_ast_patcher_key_error_membership_guard(tmp_path):
    """Verify KeyError supports membership guard when use_membership_guard is True."""
    code = '''def get_config(conf, section):
    return conf[section]
'''
    src_file = tmp_path / "config.py"
    src_file.write_text(code)

    patcher = ASTPatcher(repo_path=str(tmp_path))
    patch = patcher.generate_patch(
        file_path="config.py",
        line_number=2,
        defect_type=DefectPattern.KEY_ERROR,
        error_message="KeyError: 'database'",
        use_membership_guard=True,
    )

    assert patch is not None
    assert "section in conf" in patch.patched_line
    # Validate with ast.parse()
    ast.parse(patch.patched_code)


# ============================================================================
# 3. AST Patcher - AttributeError & NoneType (Null-Coalescing Guard)
# ============================================================================

def test_ast_patcher_attribute_error_none_type(tmp_path):
    """Verify AttributeError on NoneType inserts a null-coalescing guard."""
    code = '''def get_user_avatar(user):
    avatar_url = user.profile.avatar_url
    return avatar_url
'''
    src_file = tmp_path / "profile.py"
    src_file.write_text(code)

    patcher = ASTPatcher(repo_path=str(tmp_path))
    patch = patcher.generate_patch(
        file_path="profile.py",
        line_number=2,
        defect_type=DefectPattern.ATTRIBUTE_ERROR,
        error_message="AttributeError: 'NoneType' object has no attribute 'profile'",
    )

    assert patch is not None
    assert "user is not None" in patch.patched_line
    assert "(user.profile if user is not None else None)" in patch.patched_line
    # Validate with ast.parse()
    ast.parse(patch.patched_code)


def test_ast_patcher_none_type_subscriptable(tmp_path):
    """Verify TypeError: 'NoneType' object is not subscriptable inserts null-check."""
    code = '''def extract_first_record(db_response):
    first = db_response[0]
    return first
'''
    src_file = tmp_path / "db.py"
    src_file.write_text(code)

    patcher = ASTPatcher(repo_path=str(tmp_path))
    patch = patcher.generate_patch(
        file_path="db.py",
        line_number=2,
        defect_type="TypeError",
        error_message="TypeError: 'NoneType' object is not subscriptable",
    )

    assert patch is not None
    assert "db_response is not None" in patch.patched_line
    ast.parse(patch.patched_code)


# ============================================================================
# 4. AST Patcher - ZeroDivisionError
# ============================================================================

def test_ast_patcher_zero_division_guard(tmp_path):
    """Verify ZeroDivisionError inserts non-zero divisor guard."""
    code = '''def compute_ratio(total, count):
    ratio = total / count
    return ratio
'''
    src_file = tmp_path / "math_demo.py"
    src_file.write_text(code)

    patcher = ASTPatcher(repo_path=str(tmp_path))
    patch = patcher.generate_patch(
        file_path="math_demo.py",
        line_number=2,
        defect_type=DefectPattern.ZERO_DIVISION,
        error_message="ZeroDivisionError: division by zero",
    )

    assert patch is not None
    assert "count != 0" in patch.patched_line
    ast.parse(patch.patched_code)


# ============================================================================
# 5. AST Patcher - Apply & Rollback
# ============================================================================

def test_ast_patcher_apply_and_rollback(tmp_path):
    """Verify applying a patch modifies the file and rollback restores exact bytes."""
    code = '''def get_item(items, i):
    return items[i]
'''
    src_file = tmp_path / "service.py"
    src_file.write_text(code)

    patcher = ASTPatcher(repo_path=str(tmp_path))
    patch = patcher.generate_patch(
        file_path="service.py",
        line_number=2,
        defect_type=DefectPattern.INDEX_ERROR,
    )

    # Apply patch
    assert patcher.apply_patch(patch, backup=True) is True
    assert src_file.read_text() == patch.patched_code
    # Backup file must exist
    assert (tmp_path / "service.py.autocure_bak").exists()

    # Rollback patch
    assert patcher.rollback_patch(patch) is True
    assert src_file.read_text() == code
    # Backup file cleaned up
    assert not (tmp_path / "service.py.autocure_bak").exists()


# ============================================================================
# 6. Regression Verifier & Auto-Rollback Engine
# ============================================================================

def test_regression_verifier_heals_failing_test(tmp_path):
    """
    Verify RegressionVerifier executes pytest, discovers that the patch fixes
    the failing test, and marks verification as SUCCESS.
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    # App file with IndexError bug
    (repo / "calc.py").write_text('''def get_item(items, index):
    return items[index]
''')

    # Test file that reproduces the defect and asserts safe return
    (repo / "test_calc.py").write_text('''from calc import get_item

def test_get_item_valid():
    assert get_item([10, 20], 0) == 10

def test_get_item_out_of_bounds():
    # Fails before patch (IndexError), passes after patch (returns None)
    assert get_item([10, 20], 5) is None
''')

    patcher = ASTPatcher(repo_path=str(repo))
    verifier = RegressionVerifier(patcher=patcher)

    # Verify baseline failure
    exit_code, out, _ = verifier.execute_tests(repo_path=str(repo))
    assert exit_code != 0, "Baseline should fail on test_get_item_out_of_bounds"

    # Generate patch
    patch = patcher.generate_patch(
        file_path="calc.py",
        line_number=2,
        defect_type=DefectPattern.INDEX_ERROR,
    )
    assert patch is not None

    # Verify and heal
    result = verifier.verify_and_heal(
        patch=patch,
        repo_path=str(repo),
        auto_rollback=False,  # Retain verified patch
    )

    assert result.success is True
    assert result.tests_passed is True
    assert result.regression_detected is False
    assert result.rolled_back is False
    assert "calc.py" in patch.file_path


def test_regression_verifier_auto_rollback_on_failure(tmp_path):
    """
    Verify RegressionVerifier automatically rolls back file changes and records
    a regression warning when tests fail after patch application.
    """
    repo = tmp_path / "repo"
    repo.mkdir()

    original_code = '''def greet(name):
    return "Hello " + name
'''
    (repo / "greeting.py").write_text(original_code)

    # Test suite that expects exact string match
    (repo / "test_greeting.py").write_text('''from greeting import greet

def test_greet():
    assert greet("Alice") == "Hello Alice"
''')

    patcher = ASTPatcher(repo_path=str(repo))
    verifier = RegressionVerifier(patcher=patcher)

    # Baseline tests pass
    exit_code, _, _ = verifier.execute_tests(repo_path=str(repo))
    assert exit_code == 0

    # Create a dummy patch that causes test regression
    bad_code = '''def greet(name):
    return "Goodbye " + name
'''
    patch = ASTPatch(
        file_path="greeting.py",
        line_number=2,
        defect_type="RegressionDemo",
        original_code=original_code,
        patched_code=bad_code,
        diff="- return Hello\n+ return Goodbye",
        node_type="ast.Return",
        explanation="Regression test injection",
    )

    # Verify with auto-rollback enabled
    result = verifier.verify_and_heal(
        patch=patch,
        repo_path=str(repo),
        auto_rollback=True,
    )

    assert result.success is False
    assert result.regression_detected is True
    assert result.rolled_back is True
    assert result.warning is not None
    assert "Regression warning" in result.warning

    # File on disk MUST be restored to exact original code
    assert (repo / "greeting.py").read_text() == original_code


# ============================================================================
# 7. Standalone CLI Entrypoint ('autocure heal --check --repo <path>')
# ============================================================================

def test_cli_heal_check_mode(tmp_path):
    """
    Verify 'autocure heal --check --repo <path>' runs in CI mode:
    diagnoses the test failure, generates AST patch, verifies clean heal,
    writes report JSON, and exits with 0.
    """
    repo = tmp_path / "ci_repo"
    repo.mkdir()

    (repo / "data_store.py").write_text('''def get_val(store, key):
    return store[key]
''')

    (repo / "test_store.py").write_text('''from data_store import get_val

def test_get_val_missing_key():
    assert get_val({"a": 1}, "missing") is None
''')

    output_json = repo / "healing_report.json"

    # Run CLI command: autocure heal --check --repo <repo> -o <output_json>
    ret_code = cli_main([
        "heal",
        "--check",
        "--repo", str(repo),
        "--output", str(output_json),
    ])

    assert ret_code == 0, f"Expected CLI exit code 0, got {ret_code}"
    assert output_json.exists()

    report_data = json.loads(output_json.read_text())
    assert report_data["success"] is True
    assert report_data["tests_passed"] is True
    assert report_data["patch"]["defect_type"] == "KeyError"
    assert "store.get(key, None)" in report_data["patch"]["diff"]


def test_cli_heal_repo_not_found():
    """Verify CLI returns non-zero error when repo path does not exist."""
    ret_code = cli_main(["heal", "--repo", "/nonexistent/repo/path/xyz_999"])
    assert ret_code == 1


def test_cli_version():
    """Verify CLI --version exits cleanly."""
    with pytest.raises(SystemExit) as exc:
        cli_main(["--version"])
    assert exc.value.code == 0
