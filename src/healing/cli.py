"""
AutoCure CLI Entry Point
========================
Provides the 'autocure heal' command for local use and GitHub Actions CI integration.
Supports:
  autocure heal --check --repo <path>
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import List, Optional

# Ensure src is on sys.path
sys.path.insert(0, str(Path(__file__).parent.parent))

from healing.ast_patcher import ASTPatcher, ASTPatch
from healing.verifier import RegressionVerifier, VerificationResult

logger = logging.getLogger("autocure_cli")


def build_parser() -> argparse.ArgumentParser:
    """Construct command-line argument parser."""
    parser = argparse.ArgumentParser(
        prog="autocure",
        description="AutoCure: AI-Driven Self-Healing Software System CLI",
    )
    parser.add_argument(
        "--version", "-v", action="version", version="AutoCure 2.0.0"
    )

    subparsers = parser.add_subparsers(dest="subcommand", help="Available subcommands")

    # 'heal' subcommand
    heal_parser = subparsers.add_parser(
        "heal", help="Analyze defect and apply verified AST patches"
    )
    heal_parser.add_argument(
        "--repo",
        "-r",
        type=str,
        default=".",
        help="Path to repository or target directory (default: current working directory)",
    )
    heal_parser.add_argument(
        "--check",
        "-c",
        action="store_true",
        help="Check mode: dry-run / verify patches against tests without permanent changes",
    )
    heal_parser.add_argument(
        "--traceback",
        "-t",
        type=str,
        default=None,
        help="Path to traceback text file, or inline traceback string",
    )
    heal_parser.add_argument(
        "--log",
        "-l",
        type=str,
        default=None,
        help="Path to log file to parse for error tracebacks",
    )
    heal_parser.add_argument(
        "--file",
        "-f",
        type=str,
        default=None,
        help="Target source file to patch",
    )
    heal_parser.add_argument(
        "--line",
        type=int,
        default=None,
        help="Line number containing the defect",
    )
    heal_parser.add_argument(
        "--error",
        "-e",
        type=str,
        default=None,
        help="Defect type (IndexError, KeyError, AttributeError, ZeroDivisionError)",
    )
    heal_parser.add_argument(
        "--message",
        "-m",
        type=str,
        default="",
        help="Error message detail",
    )
    heal_parser.add_argument(
        "--test-target",
        type=str,
        default=None,
        help="Specific test file or path for pytest verification (default: repo root)",
    )
    heal_parser.add_argument(
        "--apply",
        "-a",
        action="store_true",
        help="Persist patch to disk if regression verification passes",
    )
    heal_parser.add_argument(
        "--output",
        "-o",
        type=str,
        default=None,
        help="File path to write JSON verification report (for CI artifacts)",
    )

    return parser


def handle_heal(args: argparse.Namespace) -> int:
    """Execute the 'heal' command."""
    repo_path = os.path.abspath(args.repo)
    if not os.path.exists(repo_path):
        print(f"Error: Repository path does not exist: {repo_path}", file=sys.stderr)
        return 1

    patcher = ASTPatcher(repo_path=repo_path)
    verifier = RegressionVerifier(patcher=patcher)

    patch: Optional[ASTPatch] = None

    # Case 1: Specific file, line, and error given directly
    if args.file and args.line and args.error:
        print(f"[AutoCure] Generating AST patch for {args.error} at {args.file}:{args.line}...")
        patch = patcher.generate_patch(
            file_path=args.file,
            line_number=args.line,
            defect_type=args.error,
            error_message=args.message,
            repo_path=repo_path,
        )

    # Case 2: Traceback provided via file or string
    elif args.traceback:
        tb_text = args.traceback
        if os.path.isfile(args.traceback):
            with open(args.traceback, "r", encoding="utf-8") as f:
                tb_text = f.read()
        print(f"[AutoCure] Analyzing provided traceback for {repo_path}...")
        patch = patcher.generate_patch_from_traceback(tb_text, repo_path=repo_path)

    # Case 3: Log file provided
    elif args.log and os.path.isfile(args.log):
        with open(args.log, "r", encoding="utf-8") as f:
            log_text = f.read()
        print(f"[AutoCure] Parsing log file {args.log} for defect tracebacks...")
        patch = patcher.generate_patch_from_traceback(log_text, repo_path=repo_path)

    # Case 4: Automated CI Discovery (run tests to capture failing defect)
    else:
        print(f"[AutoCure] Running baseline verification on {repo_path}...")
        exit_code, test_output, duration = verifier.execute_tests(
            repo_path=repo_path, test_target=args.test_target
        )

        if exit_code == 0:
            print(f"[AutoCure] ✓ All tests passed in {duration:.2f}s. Repository is healthy.")
            return 0

        print(f"[AutoCure] Baseline tests failed (exit code {exit_code}). Extracting traceback...")
        patch = patcher.generate_patch_from_traceback(test_output, repo_path=repo_path)

    if not patch:
        print(
            "[AutoCure] ❌ Could not generate AST patch. No recognized defect pattern located.",
            file=sys.stderr,
        )
        return 1

    print("\n[AutoCure] ==================== Generated AST Patch ====================")
    print(f"Target:      {patch.file_path}:{patch.line_number}")
    print(f"Defect:      {patch.defect_type}")
    print(f"Explanation: {patch.explanation}")
    print(f"Diff:\n{patch.diff}")
    print("========================================================================\n")

    print("[AutoCure] Running regression verification suite...")
    # In check mode, always auto_rollback to keep check non-destructive unless --apply is passed
    should_auto_rollback = args.check or (not args.apply)

    result = verifier.verify_and_heal(
        patch=patch,
        repo_path=repo_path,
        test_target=args.test_target,
        auto_rollback=should_auto_rollback,
    )

    if args.output:
        try:
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(result.to_dict(), f, indent=2)
            print(f"[AutoCure] Verification report written to: {args.output}")
        except Exception as e:
            print(f"[AutoCure] Warning: Could not write output JSON: {e}", file=sys.stderr)

    if result.success:
        print(f"[AutoCure] ✓ Patch verified successfully in {result.duration_seconds:.2f}s!")
        if should_auto_rollback:
            print("[AutoCure] (Check mode: file restored to clean state, fix verified without regression)")
        else:
            print(f"[AutoCure] Patch applied and retained in {patch.file_path}")
        return 0
    else:
        print(f"[AutoCure] ⚠️ {result.warning}", file=sys.stderr)
        return 1


def main(argv: Optional[List[str]] = None) -> int:
    """CLI entry point."""
    parser = build_parser()
    args = parser.parse_args(argv)

    if not args.subcommand:
        parser.print_help()
        return 0

    if args.subcommand == "heal":
        return handle_heal(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
