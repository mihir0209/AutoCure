"""
Unit and Adversarial Tests for Cascading AST Patching & Transactional Rollback
=============================================================================
"""

import ast
import sys
import tempfile
from pathlib import Path

SRC_DIR = str(Path(__file__).resolve().parent.parent / "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

import pytest

from healing import (
    CascadingASTPatcher,
    CallSiteMatch,
    TransactionSnapshot,
)


@pytest.fixture
def temp_project():
    """Sets up an isolated multi-file Python project fixture."""
    with tempfile.TemporaryDirectory() as tmpdir:
        root = Path(tmpdir)

        # File 1: Service definition (callee)
        service_file = root / "service.py"
        service_file.write_text(
            """def process_payment(account_id: str, amount: float):\n    return f"Paid {amount} to {account_id}"\n""",
            encoding="utf-8",
        )

        # File 2: Caller A
        caller_a = root / "caller_a.py"
        caller_a.write_text(
            """from service import process_payment\n\ndef run_a():\n    return process_payment("acc_1", 100.0)\n""",
            encoding="utf-8",
        )

        # File 3: Caller B (multiple calls)
        caller_b = root / "caller_b.py"
        caller_b.write_text(
            """import service\n\ndef run_b():\n    res1 = service.process_payment("acc_2", 200.0)\n    res2 = service.process_payment("acc_3", 300.0)\n    return (res1, res2)\n""",
            encoding="utf-8",
        )

        yield root, service_file, caller_a, caller_b


def test_discover_call_sites_across_multiple_files(temp_project):
    root, service_file, caller_a, caller_b = temp_project

    matches = CascadingASTPatcher.discover_call_sites(root, target_func="process_payment")
    assert len(matches) == 3

    # Check caller_a match
    match_a = [m for m in matches if "caller_a.py" in m.file_path]
    assert len(match_a) == 1
    assert match_a[0].arg_count == 2
    assert match_a[0].func_name == "process_payment"

    # Check caller_b matches (2 calls)
    matches_b = [m for m in matches if "caller_b.py" in m.file_path]
    assert len(matches_b) == 2


def test_synchronize_function_signature_with_default(temp_project):
    root, service_file, caller_a, caller_b = temp_project

    snapshot = TransactionSnapshot()
    result = CascadingASTPatcher.synchronize_function_signature(
        repo_path=root,
        definition_file=service_file,
        func_name="process_payment",
        new_param="currency",
        default_literal="USD",
        snapshot=snapshot,
    )

    assert result.success
    assert result.func_name == "process_payment"
    assert result.call_sites_found == 3
    assert str(service_file) in result.files_modified
    assert "+def process_payment(account_id: str, amount: float, currency='USD'):" in result.diffs[str(service_file)]

    # Verify modified code is parseable by ast
    updated_code = service_file.read_text(encoding="utf-8")
    parsed = ast.parse(updated_code)
    func_node = next(n for n in ast.walk(parsed) if isinstance(n, ast.FunctionDef))
    args = [a.arg for a in func_node.args.args]
    assert "currency" in args
    assert len(func_node.args.defaults) == 1


def test_transactional_snapshot_rollback_on_failure(temp_project):
    root, service_file, caller_a, caller_b = temp_project

    orig_service_content = service_file.read_text(encoding="utf-8")
    orig_caller_a_content = caller_a.read_text(encoding="utf-8")

    snapshot = TransactionSnapshot()
    result = CascadingASTPatcher.synchronize_function_signature(
        repo_path=root,
        definition_file=service_file,
        func_name="process_payment",
        new_param="channel",
        default_literal="WIRE",
        snapshot=snapshot,
    )

    assert result.success
    # Ensure file on disk was modified
    assert service_file.read_text(encoding="utf-8") != orig_service_content

    # Trigger transactional rollback
    snapshot.rollback()

    # Verify file is restored byte-for-byte to original
    assert service_file.read_text(encoding="utf-8") == orig_service_content
    assert caller_a.read_text(encoding="utf-8") == orig_caller_a_content


def test_handles_nonexistent_function_gracefully(temp_project):
    root, service_file, caller_a, caller_b = temp_project

    result = CascadingASTPatcher.synchronize_function_signature(
        repo_path=root,
        definition_file=service_file,
        func_name="nonexistent_function",
        new_param="arg1",
        default_literal=None,
    )

    assert not result.success
    assert "not found" in result.error.lower()
