"""CI integration layer: run change-aware test selection, then pytest on the selected files.

Consumes only the JSON output of ``python -m change_aware select-tests``. The core engine
has no knowledge of this script or of GitHub Actions, so the same logic runs locally:

    python .github/scripts/run_change_aware_tests.py --base <sha> --head <sha> [--repo .]
        [--report-dir DIR]

With ``--report-dir`` it also writes ``selection.json`` and ``execution.json`` for the
summary generator. Exits with pytest's exit code; report writing can never change it.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

# Final pytest line, e.g. "2 passed in 0.05s" or "== 1 failed, 3 passed in 1.2s ==".
_PYTEST_RESULT_LINE = re.compile(r"(no tests ran|\d+ \w+).* in [\d.]+s")


def select_tests(repo: str, base: str, head: str) -> tuple[dict | None, str | None]:
    """Return ``(selection, None)`` on success or ``(None, error message)`` on failure."""
    completed = subprocess.run(
        [sys.executable, "-m", "change_aware", "select-tests", repo, base, head, "--format", "json"],
        capture_output=True,
        text=True,
    )
    # Analyzer logs go to stderr; keep them visible without mixing them into the JSON.
    stderr = completed.stderr.strip()
    if stderr:
        print("Analyzer log:", file=sys.stderr)
        print(stderr, file=sys.stderr)
    if completed.returncode != 0:
        last_line = stderr.splitlines()[-1] if stderr else "no error output"
        return None, f"analyzer exited with code {completed.returncode}: {last_line}"
    try:
        selection = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        return None, f"analyzer produced invalid JSON: {exc}"
    paths = selection.get("selected_test_paths") if isinstance(selection, dict) else None
    if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
        return None, "analyzer JSON has no valid 'selected_test_paths' list"
    return selection, None


def run_pytest(repo: str, test_paths: list[str]) -> tuple[int, str | None]:
    """Run pytest, streaming its output. Return ``(exit code, final result line)``."""
    process = subprocess.Popen(
        [sys.executable, "-m", "pytest", *test_paths],
        cwd=repo,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        errors="replace",
    )
    result_line: str | None = None
    assert process.stdout is not None
    for line in process.stdout:
        print(line, end="", flush=True)
        stripped = line.strip().strip("=").strip()
        if _PYTEST_RESULT_LINE.search(stripped):
            result_line = stripped
    return process.wait(), result_line


def write_reports(report_dir: str, selection: dict | None, execution: dict) -> None:
    try:
        directory = Path(report_dir)
        directory.mkdir(parents=True, exist_ok=True)
        if selection is not None:
            (directory / "selection.json").write_text(json.dumps(selection, indent=2), "utf-8")
        (directory / "execution.json").write_text(json.dumps(execution, indent=2), "utf-8")
    except OSError as exc:
        print(f"Warning: could not write report files to {report_dir}: {exc}", file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=".")
    parser.add_argument("--base", required=True, help="Base commit SHA")
    parser.add_argument("--head", required=True, help="Head commit SHA")
    parser.add_argument("--report-dir", help="Directory for selection.json / execution.json")
    args = parser.parse_args(argv)

    print("Change-Aware Testing")
    print("====================")
    print()
    print(f"Base commit: {args.base}")
    print(f"Head commit: {args.head}")
    print()

    selection, analysis_error = select_tests(args.repo, args.base, args.head)
    selected: list[str] = selection["selected_test_paths"] if selection else []

    fallback_reason: str | None = None
    if selection is None:
        fallback_reason = "analysis_failed"
        print(f"Change-aware analysis failed: {analysis_error}")
        print("Falling back to the full test suite for safety.")
    elif not selected:
        fallback_reason = "no_tests_selected"
        print("No tests were selected by the change-aware analyzer.")
        print("Falling back to the full test suite for safety.")
    else:
        summary = selection.get("summary", {})
        print("Change-aware test selection completed.")
        print()
        print("Selected tests:")
        for path in selected:
            print(f"  {path}")
        print()
        print(f"Number selected: {len(selected)}")
        if summary:
            print(f"Total tests: {summary.get('total_tests')}  "
                  f"Skipped: {summary.get('skipped')}  "
                  f"Reduction: {summary.get('reduction_percentage')}%")
        print()
        print(f"Running {len(selected)} selected test file(s)...")
    print(flush=True)

    exit_code, result_line = run_pytest(args.repo, selected)
    print()
    print(f"pytest exited with code {exit_code}")

    if args.report_dir:
        write_reports(args.report_dir, selection, {
            "base_commit": args.base,
            "head_commit": args.head,
            "mode": "fallback" if fallback_reason else "selected",
            "fallback_reason": fallback_reason,
            "analysis_error": analysis_error,
            "executed_test_paths": selected,
            "pytest_exit_code": exit_code,
            "pytest_result": result_line,
        })
    return exit_code


if __name__ == "__main__":
    sys.exit(main())
