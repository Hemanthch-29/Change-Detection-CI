"""CI reporting layer: render a Markdown summary of a change-aware test run.

Reads ``selection.json`` (analyzer output) and ``execution.json`` (runner output) from
``--report-dir``. Output goes to ``--output`` if given, else appended to
``$GITHUB_STEP_SUMMARY`` if set, else printed to stdout.

Reporting is best-effort: this script always exits 0 so it can never change the job result.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any

MAX_ROWS = 100  # keep the summary well under GitHub's step-summary size limit

_PYTEST_EXIT_CODES = {
    0: "all tests passed",
    1: "some tests failed",
    2: "test run interrupted",
    3: "internal pytest error",
    4: "pytest usage error",
    5: "no tests collected",
}


def _code(value: object) -> str:
    text = str(value).replace("`", "'").replace("|", "\\|").replace("\n", " ")
    return f"`{text}`"


def _cell(value: object) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _truncated(items: list[Any]) -> tuple[list[Any], str | None]:
    if len(items) <= MAX_ROWS:
        return items, None
    return items[:MAX_ROWS], f"_... and {len(items) - MAX_ROWS} more not shown._"


def render_summary(selection: dict[str, Any] | None, execution: dict[str, Any] | None) -> str:
    lines: list[str] = ["# Change-Aware Testing", ""]
    execution = execution or {}

    lines += ["## Change Analysis", ""]
    lines.append(f"- Base commit: {_code(execution.get('base_commit', 'unknown'))}")
    lines.append(f"- Head commit: {_code(execution.get('head_commit', 'unknown'))}")
    lines.append("")

    if selection is None:
        error = execution.get("analysis_error") or "no analyzer output was available"
        lines += [f"> Change-aware analysis did not produce results: {_cell(error)}", ""]
    else:
        lines += _changed_files_section(selection)
        lines += _impacted_section(selection)
        lines += _selection_section(selection, fallback=execution.get("mode") == "fallback")

    lines += _execution_section(execution)
    return "\n".join(lines).rstrip() + "\n"


def _changed_files_section(selection: dict[str, Any]) -> list[str]:
    lines = ["## Changed Files", ""]
    changed = selection.get("changed_files")
    if changed is None:
        # Older analyzer output without change types.
        changed = [{"path": p} for p in selection.get("changed_components", [])]
    if not changed:
        return lines + ["_No files changed._", ""]
    shown, more = _truncated(changed)
    for item in shown:
        entry = f"- {_code(item.get('path'))}"
        if item.get("change_type"):
            entry += f" — {item['change_type']}"
        if item.get("change_type") == "RENAMED" and item.get("old_path"):
            entry += f" (from {_code(item['old_path'])})"
        lines.append(entry)
    if more:
        lines.append(more)
    return lines + [""]


def _impacted_section(selection: dict[str, Any]) -> list[str]:
    lines = ["## Impacted Components", ""]
    impacted = selection.get("impacted_components") or []
    if not impacted:
        return lines + ["_No impacted components._", ""]
    lines += ["| Component | Depth | Direct Change | Reason |", "|---|---:|---|---|"]
    shown, more = _truncated(impacted)
    for c in shown:
        direct = "Yes" if c.get("directly_changed") else "No"
        lines.append(
            f"| {_code(c.get('path'))} | {c.get('depth', '')} | {direct} | {_cell(c.get('reason', ''))} |"
        )
    if more:
        lines += ["", more]
    return lines + [""]


def _selection_section(selection: dict[str, Any], fallback: bool = False) -> list[str]:
    summary = selection.get("summary") or {}
    reduction = f"{summary.get('reduction_percentage', 'n/a')}%"
    if fallback:
        reduction += " (not applied: the full suite was executed as a fallback)"
    lines = [
        "## Test Selection",
        "",
        f"- Total discovered tests: {summary.get('total_tests', 'n/a')}",
        f"- Selected tests: {summary.get('selected', 'n/a')}",
        f"- Skipped tests: {summary.get('skipped', 'n/a')}",
        f"- Reduction: {reduction}",
        "",
    ]
    selected = selection.get("selected_tests") or []
    if not selected:
        return lines + ["_No tests were selected._", ""]
    lines += ["| Test | Reason | Impacted By |", "|---|---|---|"]
    shown, more = _truncated(selected)
    for t in shown:
        reasons = ", ".join(t.get("reasons") or [])
        impacted_by = ", ".join(_code(p) for p in t.get("impacted_by") or [])
        lines.append(f"| {_code(t.get('path'))} | {_cell(reasons)} | {impacted_by} |")
    if more:
        lines += ["", more]
    return lines + [""]


def _execution_section(execution: dict[str, Any]) -> list[str]:
    lines = ["## Test Execution", ""]
    if not execution:
        return lines + ["_No execution record found; the test step may not have run._", ""]

    if execution.get("mode") == "fallback":
        lines.append("**Full-suite fallback was used.**")
        lines.append("")
        if execution.get("fallback_reason") == "analysis_failed":
            lines.append(f"Reason: change-aware analysis failed ({_cell(execution.get('analysis_error'))}).")
        else:
            lines.append("Reason: no tests were selected by the change-aware analyzer.")
        lines += ["", "Executed: full test suite", ""]
    else:
        executed = execution.get("executed_test_paths") or []
        lines.append(f"Executed {len(executed)} selected test file(s):")
        lines.append("")
        shown, more = _truncated(executed)
        lines += [f"- {_code(p)}" for p in shown]
        if more:
            lines.append(more)
        lines.append("")

    exit_code = execution.get("pytest_exit_code")
    if isinstance(exit_code, int):
        status = "PASSED" if exit_code == 0 else "FAILED"
        meaning = _PYTEST_EXIT_CODES.get(exit_code, "unknown")
    else:
        status, meaning = "UNKNOWN", "unknown"
    lines += [
        f"- pytest result: {_cell(execution.get('pytest_result') or 'not available')}",
        f"- Exit code: {exit_code} ({meaning})",
        f"- Status: **{status}**",
        "",
    ]
    return lines


def _load(path: Path) -> dict[str, Any] | None:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        print(f"Warning: could not read {path}: {exc}", file=sys.stderr)
        return None
    return data if isinstance(data, dict) else None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--report-dir", required=True)
    parser.add_argument("--output", help="Write the summary here instead of $GITHUB_STEP_SUMMARY")
    args = parser.parse_args(argv)

    try:
        report_dir = Path(args.report_dir)
        markdown = render_summary(
            _load(report_dir / "selection.json"), _load(report_dir / "execution.json")
        )
        target = args.output or os.environ.get("GITHUB_STEP_SUMMARY")
        if target:
            with open(target, "a", encoding="utf-8") as handle:
                handle.write(markdown)
            print(f"Summary written to {target}")
        else:
            print(markdown)
    except Exception as exc:  # noqa: BLE001 - reporting must never fail the job
        print(f"Warning: could not generate change-aware summary: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
