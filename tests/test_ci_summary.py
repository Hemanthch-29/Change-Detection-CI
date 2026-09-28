"""Tests for the CI summary generator in .github/scripts (reporting layer, not the core engine)."""

import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / ".github" / "scripts" / "generate_change_aware_summary.py"
_spec = importlib.util.spec_from_file_location("generate_change_aware_summary", SCRIPT)
summary = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(summary)

SELECTION = {
    "changed_files": [
        {"path": "src/payment/service.py", "change_type": "MODIFIED", "old_path": "src/payment/service.py"},
        {"path": "src/payment/tax.py", "change_type": "ADDED", "old_path": None},
    ],
    "changed_components": ["src/payment/service.py", "src/payment/tax.py"],
    "impacted_components": [
        {"path": "src/payment/service.py", "depth": 0, "directly_changed": True, "reason": "modified"},
        {"path": "src/checkout/service.py", "depth": 1, "directly_changed": False,
         "reason": "depends on src/payment/service.py"},
    ],
    "selected_tests": [
        {"path": "tests/payment/test_service.py",
         "reasons": ["test imports impacted component", "test matches impacted component by naming convention"],
         "impacted_by": ["src/payment/service.py"]},
    ],
    "skipped_tests": ["tests/user/test_service.py"],
    "selected_test_paths": ["tests/payment/test_service.py"],
    "summary": {"total_tests": 2, "selected": 1, "skipped": 1, "reduction_percentage": 50.0},
}


def _execution(**overrides: object) -> dict:
    base = {
        "base_commit": "aaa111",
        "head_commit": "bbb222",
        "mode": "selected",
        "fallback_reason": None,
        "analysis_error": None,
        "executed_test_paths": ["tests/payment/test_service.py"],
        "pytest_exit_code": 0,
        "pytest_result": "1 passed in 0.01s",
    }
    return {**base, **overrides}


def test_selected_tests_pass() -> None:
    md = summary.render_summary(SELECTION, _execution())

    assert "# Change-Aware Testing" in md
    assert "- Base commit: `aaa111`" in md and "- Head commit: `bbb222`" in md
    assert "- `src/payment/service.py` — MODIFIED\n" in md
    assert "- `src/payment/tax.py` — ADDED" in md
    assert "| `src/checkout/service.py` | 1 | No | depends on src/payment/service.py |" in md
    assert "- Reduction: 50.0%" in md
    assert "- Total discovered tests: 2" in md
    assert "test imports impacted component, test matches impacted component by naming convention" in md
    assert "Executed 1 selected test file(s):" in md
    assert "- pytest result: 1 passed in 0.01s" in md
    assert "- Exit code: 0 (all tests passed)" in md
    assert "- Status: **PASSED**" in md
    assert "fallback" not in md.lower()


def test_selected_tests_fail() -> None:
    md = summary.render_summary(
        SELECTION, _execution(pytest_exit_code=1, pytest_result="1 failed in 0.02s")
    )
    assert "- Exit code: 1 (some tests failed)" in md
    assert "- Status: **FAILED**" in md


def test_no_tests_selected_fallback() -> None:
    selection = {**SELECTION, "selected_tests": [], "selected_test_paths": []}
    md = summary.render_summary(
        selection, _execution(mode="fallback", fallback_reason="no_tests_selected", executed_test_paths=[])
    )
    assert "**Full-suite fallback was used.**" in md
    assert "no tests were selected by the change-aware analyzer" in md
    assert "_No tests were selected._" in md
    assert "(not applied: the full suite was executed as a fallback)" in md


def test_renamed_file_shows_old_path() -> None:
    selection = {**SELECTION, "changed_files": [
        {"path": "src/new.py", "change_type": "RENAMED", "old_path": "src/old.py"},
    ]}
    md = summary.render_summary(selection, _execution())
    assert "- `src/new.py` — RENAMED (from `src/old.py`)" in md


def test_analysis_failed_fallback() -> None:
    md = summary.render_summary(None, _execution(
        mode="fallback",
        fallback_reason="analysis_failed",
        analysis_error="analyzer exited with code 1: Error: Commit not found: 'x'",
        executed_test_paths=[],
    ))
    assert "**Full-suite fallback was used.**" in md
    assert "change-aware analysis failed" in md
    assert "Commit not found" in md
    assert "## Changed Files" not in md


def test_missing_execution_record() -> None:
    md = summary.render_summary(None, None)
    assert "No execution record found" in md


def test_table_cells_are_escaped() -> None:
    selection = {**SELECTION, "impacted_components": [
        {"path": "src/a|b.py", "depth": 0, "directly_changed": True, "reason": "x|y"},
    ]}
    md = summary.render_summary(selection, _execution())
    assert "| `src/a\\|b.py` | 0 | Yes | x\\|y |" in md


def test_main_writes_to_step_summary_and_always_exits_zero(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    report_dir = tmp_path / "report"
    report_dir.mkdir()
    (report_dir / "selection.json").write_text(json.dumps(SELECTION), encoding="utf-8")
    (report_dir / "execution.json").write_text("{not valid json", encoding="utf-8")
    step_summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(step_summary))

    assert summary.main(["--report-dir", str(report_dir)]) == 0
    content = step_summary.read_text(encoding="utf-8")
    assert "## Changed Files" in content
    assert "No execution record found" in content


def test_main_prints_to_stdout_without_step_summary(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("GITHUB_STEP_SUMMARY", raising=False)
    assert summary.main(["--report-dir", str(tmp_path / "missing")]) == 0
    assert "# Change-Aware Testing" in capsys.readouterr().out
