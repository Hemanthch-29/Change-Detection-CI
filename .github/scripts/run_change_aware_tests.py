"""CI integration layer: run change-aware test selection, then pytest on the selected files.

Consumes only the JSON output of ``python -m change_aware select-tests``. The core engine
has no knowledge of this script or of GitHub Actions, so the same logic runs locally:

    python .github/scripts/run_change_aware_tests.py --base <sha> --head <sha> [--repo .]

Exits with pytest's exit code.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys


def select_tests(repo: str, base: str, head: str) -> dict | None:
    """Return the parsed selection JSON, or None if the analyzer failed."""
    completed = subprocess.run(
        [sys.executable, "-m", "change_aware", "select-tests", repo, base, head, "--format", "json"],
        capture_output=True,
        text=True,
    )
    # Analyzer logs go to stderr; keep them visible without mixing them into the JSON.
    if completed.stderr.strip():
        print("Analyzer log:", file=sys.stderr)
        print(completed.stderr.rstrip(), file=sys.stderr)
    if completed.returncode != 0:
        print(f"Change-aware analyzer exited with code {completed.returncode}.")
        return None
    try:
        selection = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        print(f"Change-aware analyzer produced invalid JSON: {exc}")
        return None
    paths = selection.get("selected_test_paths") if isinstance(selection, dict) else None
    if not isinstance(paths, list) or not all(isinstance(p, str) for p in paths):
        print("Change-aware analyzer JSON has no valid 'selected_test_paths' list.")
        return None
    return selection


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--repo", default=".")
    parser.add_argument("--base", required=True, help="Base commit SHA")
    parser.add_argument("--head", required=True, help="Head commit SHA")
    args = parser.parse_args(argv)

    print("Change-Aware Testing")
    print("====================")
    print()
    print(f"Base commit: {args.base}")
    print(f"Head commit: {args.head}")
    print()

    selection = select_tests(args.repo, args.base, args.head)
    selected: list[str] = selection["selected_test_paths"] if selection else []

    if selection is None:
        print("Change-aware analysis failed.")
        print("Falling back to the full test suite for safety.")
    elif not selected:
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

    result = subprocess.run([sys.executable, "-m", "pytest", *selected], cwd=args.repo)
    print()
    print(f"pytest exited with code {result.returncode}")
    return result.returncode


if __name__ == "__main__":
    sys.exit(main())
