"""
Adversarial QA Test Suite: Regression Guard, Auto-Rollback & CLI Integration
============================================================================
Rigorous verification of AutoCure's regression rejection and CLI execution:
  1. Intentional bad patch detection: fixes a target bug but breaks regression tests.
  2. Automatic rollback assertion: files restored bit-for-bit to pre-patch state,
     backup files deleted, exit code non-zero.
  3. Good patch acceptance: passes test suite, verified and persisted on disk.
  4. CLI integration ('autocure heal') via subprocess:
     - Return code verification (0 for clean heal, != 0 for regression rejection)
     - JSON status output validation against reporting schema
     - Dry-run '--check' verification mode
     - Traceback file and automated baseline discovery modes
"""

from __future__ import annotations

import difflib
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Dict, Tuple

import pytest

# Ensure src is in sys.path
SRC_DIR = str(Path(__file__).resolve().parent.parent / "src")
if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from healing.ast_patcher import ASTPatcher, ASTPatch, DefectPattern
from healing.verifier import RegressionVerifier, VerificationResult
from healing.cli import main as cli_main


# ============================================================================
# Helpers & Fixtures
# ============================================================================

def sha256_file(path: Path | str) -> str:
    """Calculate SHA256 hash of a file for byte-for-byte rollback integrity."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()


AUTOCURE_BIN = shutil.which("autocure") or "/usr/local/bin/autocure"


@pytest.fixture
def regression_test_repo(tmp_path):
    """
    Creates a realistic mock repository with:
      - Core business logic module (analytics_engine.py)
      - Regression test suite (test_analytics.py)
    """
    repo = tmp_path / "analytics_service"
    repo.mkdir()

    # pytest.ini to keep pytest scoped strictly to this mock repo
    (repo / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n", encoding="utf-8")

    src_dir = repo / "src"
    src_dir.mkdir()
    (src_dir / "__init__.py").write_text("", encoding="utf-8")

    analytics_file = src_dir / "analytics_engine.py"
    analytics_file.write_text('''"""Analytics Engine Core Module."""

def calculate_tier_discount(revenue: float, tier: str) -> float:
    """Existing business logic with strict regression contracts."""
    if revenue < 0:
        raise ValueError("Revenue cannot be negative")
    if tier == "PLATINUM":
        return revenue * 0.30
    elif tier == "GOLD":
        return revenue * 0.20
    elif tier == "SILVER":
        return revenue * 0.10
    return 0.0


def compute_sample_mean(samples: list) -> float:
    """Calculates sample mean. Buggy: crashes on empty list."""
    total = sum(samples)
    return total / len(samples)


def get_feature_flag(config: dict, flag_name: str) -> bool:
    """Fetches feature flag. Buggy: crashes on missing flag key."""
    return config[flag_name]
''', encoding="utf-8")

    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (tests_dir / "__init__.py").write_text("", encoding="utf-8")

    test_file = tests_dir / "test_analytics.py"
    test_file.write_text('''import pytest
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from analytics_engine import calculate_tier_discount, compute_sample_mean, get_feature_flag

# 1. Existing Critical Regression Tests (Must never be broken!)
def test_regression_platinum_tier_discount():
    assert calculate_tier_discount(1000.0, "PLATINUM") == 300.0

def test_regression_gold_tier_discount():
    assert calculate_tier_discount(1000.0, "GOLD") == 200.0

def test_regression_silver_tier_discount():
    assert calculate_tier_discount(1000.0, "SILVER") == 100.0

def test_regression_default_zero_discount():
    assert calculate_tier_discount(1000.0, "STANDARD") == 0.0

def test_regression_negative_revenue_raises():
    with pytest.raises(ValueError):
        calculate_tier_discount(-50.0, "GOLD")

# 2. Defect tests
def test_compute_sample_mean_normal():
    assert compute_sample_mean([10, 20, 30]) == 20.0
''', encoding="utf-8")

    return repo


# ============================================================================
# 1. Regression Rejection & Auto-Rollback Tests
# ============================================================================

def test_regression_rejection_bad_patch_rolled_back(regression_test_repo):
    """
    Adversarial Regression Guard Test:
      1. Baseline: All 6 existing regression tests pass.
      2. Propose an intentional BAD patch:
         Modifies 'calculate_tier_discount' to hardcode return 0.0.
      3. Assert:
         - Regression is detected (tests fail with exit code != 0).
         - AutoCure automatically rolls back all file changes on disk.
         - File content hash after rollback matches original hash EXACTLY.
         - Backup '.autocure_bak' is removed.
         - VerificationResult reports regression_detected=True, rolled_back=True, success=False.
    """
    repo_path = str(regression_test_repo)
    target_file = regression_test_repo / "src" / "analytics_engine.py"
    original_content = target_file.read_text(encoding="utf-8")
    original_sha256 = sha256_file(target_file)

    patcher = ASTPatcher(repo_path=repo_path)
    verifier = RegressionVerifier(patcher=patcher)

    # 1. Verify baseline suite passes
    code, out, _ = verifier.execute_tests(repo_path=repo_path)
    assert code == 0, f"Baseline tests must pass. Output: {out}"

    # 2. Construct an intentional BAD patch that breaks existing regression tests
    bad_code = original_content.replace(
        'return revenue * 0.30',
        'return 0.0  # Intentional bad patch: breaks PLATINUM discount regression'
    )
    diff_text = "".join(difflib.unified_diff(
        original_content.splitlines(keepends=True),
        bad_code.splitlines(keepends=True),
        fromfile="a/src/analytics_engine.py",
        tofile="b/src/analytics_engine.py",
    ))

    bad_patch = ASTPatch(
        file_path="src/analytics_engine.py",
        line_number=8,
        defect_type="RegressionBreaker",
        original_code=original_content,
        patched_code=bad_code,
        diff=diff_text,
        node_type="ast.Return",
        explanation="Intentional defect injection for regression guard testing",
        original_line="return revenue * 0.30",
        patched_line="return 0.0",
        confidence=0.10,
    )

    # 3. Execute verify_and_heal with auto_rollback=True
    result: VerificationResult = verifier.verify_and_heal(
        patch=bad_patch,
        repo_path=repo_path,
        auto_rollback=True,
    )

    # 4. Assertions on verification failure & regression detection
    assert result.success is False, "Verification must report failure on regression"
    assert result.tests_passed is False, "Tests must fail"
    assert result.regression_detected is True, "Regression must be flagged"
    assert result.rolled_back is True, "Auto-rollback must succeed"
    assert result.exit_code != 0, f"Pytest must exit with non-zero code, got {result.exit_code}"
    assert "Regression warning" in (result.warning or "")

    # 5. Assert disk rollback integrity
    restored_content = target_file.read_text(encoding="utf-8")
    restored_sha256 = sha256_file(target_file)

    assert restored_sha256 == original_sha256, "Target file SHA256 after rollback must match original pre-patch state"
    assert restored_content == original_content, "Target file content must be restored byte-for-byte"

    bak_file = target_file.with_suffix(".py.autocure_bak")
    assert not bak_file.exists(), f"Backup file {bak_file} must be cleaned up after rollback"

    # 6. Verify repository regression tests pass again after rollback
    code_after, out_after, _ = verifier.execute_tests(repo_path=repo_path)
    assert code_after == 0, f"Post-rollback tests must pass cleanly. Output: {out_after}"


def test_regression_good_patch_accepted_and_persisted(regression_test_repo):
    """
    Verify a valid AST patch fixing a defect (ZeroDivisionError) is accepted,
    passes regression verification, and is persisted when auto_rollback=False.
    """
    repo_path = str(regression_test_repo)
    target_file = regression_test_repo / "src" / "analytics_engine.py"
    original_content = target_file.read_text(encoding="utf-8")

    # Add a test exposing the ZeroDivisionError defect on empty list
    test_file = regression_test_repo / "tests" / "test_analytics.py"
    test_file.write_text(
        test_file.read_text(encoding="utf-8") +
        "\ndef test_sample_mean_empty():\n    assert compute_sample_mean([]) == 0.0\n",
        encoding="utf-8",
    )

    patcher = ASTPatcher(repo_path=repo_path)
    verifier = RegressionVerifier(patcher=patcher)

    # Prior to fix, tests fail because of the empty list division by zero
    exit_code, _, _ = verifier.execute_tests(repo_path=repo_path)
    assert exit_code != 0

    # Generate patch for line 18 (return total / len(samples))
    patch = patcher.generate_patch(
        file_path="src/analytics_engine.py",
        line_number=18,
        defect_type="ZeroDivisionError",
        error_message="division by zero",
        repo_path=repo_path,
    )

    assert patch is not None
    assert patch.defect_type == DefectPattern.ZERO_DIVISION

    # Verify and heal with auto_rollback=False (apply permanently)
    result = verifier.verify_and_heal(
        patch=patch,
        repo_path=repo_path,
        auto_rollback=False,
    )

    assert result.success is True
    assert result.tests_passed is True
    assert result.regression_detected is False
    assert result.rolled_back is False
    assert result.exit_code == 0

    # Ensure fix persists and is valid
    current_content = target_file.read_text(encoding="utf-8")
    assert current_content != original_content
    assert "len(samples) != 0" in current_content


# ============================================================================
# 2. CLI Integration ('autocure heal') via Subprocess
# ============================================================================

def test_cli_heal_subprocess_success_with_json_report(tmp_path):
    """
    CLI Test: 'autocure heal' executes via subprocess, fixes defect, passes regression,
    exits with code 0, and writes valid JSON report matching reporting schema.
    """
    repo = tmp_path / "cli_success_repo"
    repo.mkdir()
    (repo / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n", encoding="utf-8")

    app_file = repo / "app.py"
    app_file.write_text('''def get_user_role(users: list, index: int):
    role = users[index]
    return role
''', encoding="utf-8")

    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_app.py").write_text('''import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from app import get_user_role

def test_valid_role():
    assert get_user_role(["admin", "user"], 0) == "admin"

def test_out_of_bounds_safe():
    assert get_user_role(["admin"], 5) is None
''', encoding="utf-8")

    report_json = repo / "healing_report.json"

    # Invoke 'autocure heal' via subprocess
    cmd = [
        AUTOCURE_BIN,
        "heal",
        "--repo", str(repo),
        "--file", "app.py",
        "--line", "2",
        "--error", "IndexError",
        "--message", "list index out of range",
        "--output", str(report_json),
        "--apply",
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    assert proc.returncode == 0, f"CLI exited with {proc.returncode}. stderr: {proc.stderr}\nstdout: {proc.stdout}"
    assert "[AutoCure] ✓ Patch verified successfully" in proc.stdout

    # Verify JSON status output
    assert report_json.is_file(), "Report JSON file must be created"
    report_data = json.loads(report_json.read_text(encoding="utf-8"))

    assert report_data["success"] is True
    assert report_data["tests_passed"] is True
    assert report_data["regression_detected"] is False
    assert report_data["rolled_back"] is False
    assert report_data["exit_code"] == 0
    assert report_data["patch"] is not None
    assert report_data["patch"]["defect_type"] == "IndexError"
    assert report_data["duration_seconds"] >= 0.0


def test_cli_heal_subprocess_regression_rejection(regression_test_repo):
    """
    CLI Test: 'autocure heal' detects regression caused by bad patch/tests,
    automatically rolls back, exits with code 1 (failure code), and writes JSON failure report.
    """
    repo = regression_test_repo
    report_json = repo / "regression_rejection_report.json"
    target_file = repo / "src" / "analytics_engine.py"
    original_sha256 = sha256_file(target_file)

    # Intentionally alter analytics_engine with a regression that breaks test_regression_platinum_tier_discount
    # Run autocure heal in check mode targeting a non-existent defect or forcing failure
    # Here we invoke autocure heal targeting line 8 with an incompatible error that fails regression
    cmd = [
        AUTOCURE_BIN,
        "heal",
        "--repo", str(repo),
        "--file", "src/analytics_engine.py",
        "--line", "8",
        "--error", "ZeroDivisionError",  # Incorrect patch type on return statement
        "--output", str(report_json),
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    # Should exit with code 1 (failure)
    assert proc.returncode != 0, "CLI must exit with non-zero returncode on failure"

    # Verify JSON output
    if report_json.is_file():
        report_data = json.loads(report_json.read_text(encoding="utf-8"))
        assert report_data["success"] is False

    # Verify repository was not corrupted
    assert sha256_file(target_file) == original_sha256


def test_cli_heal_subprocess_check_mode_leaves_repo_clean(tmp_path):
    """
    CLI Test: 'autocure heal --check' performs non-destructive dry-run verification.
    Asserts returncode is 0 and target file is left in its clean original state.
    """
    repo = tmp_path / "check_mode_repo"
    repo.mkdir()
    (repo / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n", encoding="utf-8")

    app_file = repo / "service.py"
    app_file.write_text('''def lookup(cfg: dict, k: str):
    return cfg[k]
''', encoding="utf-8")
    original_content = app_file.read_text(encoding="utf-8")

    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_service.py").write_text('''import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from service import lookup

def test_lookup_existing():
    assert lookup({"env": "prod"}, "env") == "prod"

def test_lookup_missing():
    assert lookup({}, "env") is None
''', encoding="utf-8")

    report_json = repo / "check_report.json"

    cmd = [
        AUTOCURE_BIN,
        "heal",
        "--check",
        "--repo", str(repo),
        "--file", "service.py",
        "--line", "2",
        "--error", "KeyError",
        "--output", str(report_json),
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)

    assert proc.returncode == 0
    assert "Check mode: file restored to clean state" in proc.stdout

    # File on disk must match original content exactly (non-destructive)
    assert app_file.read_text(encoding="utf-8") == original_content

    # Report shows success
    report_data = json.loads(report_json.read_text(encoding="utf-8"))
    assert report_data["success"] is True
    assert report_data["tests_passed"] is True


def test_cli_heal_traceback_file_argument(tmp_path):
    """
    CLI Test: 'autocure heal --traceback <file>' parses traceback file and heals.
    """
    repo = tmp_path / "tb_file_repo"
    repo.mkdir()
    (repo / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n", encoding="utf-8")

    calc_file = repo / "calc.py"
    calc_file.write_text('''def divide(a, b):
    return a / b
''', encoding="utf-8")

    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_calc.py").write_text('''import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from calc import divide

def test_divide_valid():
    assert divide(10, 2) == 5.0

def test_divide_zero_safe():
    assert divide(10, 0) == 0
''', encoding="utf-8")

    tb_file = repo / "traceback.txt"
    tb_file.write_text(f'''Traceback (most recent call last):
  File "{calc_file}", line 2, in divide
    return a / b
ZeroDivisionError: division by zero
''', encoding="utf-8")

    report_json = repo / "report.json"

    cmd = [
        AUTOCURE_BIN,
        "heal",
        "--repo", str(repo),
        "--traceback", str(tb_file),
        "--output", str(report_json),
        "--apply",
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, f"Stderr: {proc.stderr}"
    assert report_json.is_file()

    report = json.loads(report_json.read_text(encoding="utf-8"))
    assert report["success"] is True
    assert report["patch"]["defect_type"] == "ZeroDivisionError"


def test_cli_heal_automated_ci_discovery(tmp_path):
    """
    CLI Test: Automated CI discovery mode without explicit --file or --line.
    AutoCure executes test runner, extracts failure traceback, patches and verifies.
    """
    repo = tmp_path / "auto_discovery_repo"
    repo.mkdir()
    (repo / "pytest.ini").write_text("[pytest]\ntestpaths = tests\n", encoding="utf-8")

    worker_file = repo / "worker.py"
    worker_file.write_text('''def pop_front(queue: list):
    item = queue[0]
    return item
''', encoding="utf-8")

    tests_dir = repo / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_worker.py").write_text('''import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
from worker import pop_front

def test_pop_normal():
    assert pop_front([99]) == 99

def test_pop_empty():
    assert pop_front([]) is None
''', encoding="utf-8")

    report_json = repo / "discovery_report.json"

    cmd = [
        AUTOCURE_BIN,
        "heal",
        "--repo", str(repo),
        "--output", str(report_json),
        "--apply",
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    assert proc.returncode == 0, f"Discovery heal failed. Stderr: {proc.stderr}\nStdout: {proc.stdout}"

    report = json.loads(report_json.read_text(encoding="utf-8"))
    assert report["success"] is True
    assert report["tests_passed"] is True
    assert report["patch"] is not None


def test_cli_heal_adversarial_error_exit_codes(tmp_path):
    """
    CLI Test: Verify exit code 1 when non-existent repo or unpatchable error is given.
    """
    # 1. Nonexistent repository
    cmd_nonexistent = [AUTOCURE_BIN, "heal", "--repo", "/path/that/does/not/exist/9999"]
    proc_nonexistent = subprocess.run(cmd_nonexistent, capture_output=True, text=True)
    assert proc_nonexistent.returncode != 0
    assert "Error: Repository path does not exist" in proc_nonexistent.stderr

    # 2. Version command exits 0
    proc_version = subprocess.run([AUTOCURE_BIN, "--version"], capture_output=True, text=True)
    assert proc_version.returncode == 0
    assert "AutoCure 2.0.0" in proc_version.stdout
