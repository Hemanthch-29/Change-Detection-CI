import os
import subprocess
import sys
from pathlib import Path

import change_aware
from change_aware.cli import main
from change_aware.models import (
    ChangedFile,
    DependencyEdge,
    DependencyNode,
    ImpactedComponent,
    TestCandidate,
    TestSelectionResult,
)


def test_package_imports() -> None:
    assert change_aware.__version__


def test_models_can_be_instantiated() -> None:
    assert ChangedFile(path="a.py").path == "a.py"
    assert DependencyNode(id="a").id == "a"
    assert DependencyEdge(source="a", target="b").target == "b"
    assert ImpactedComponent(id="a").id == "a"
    candidate = TestCandidate(path="tests/test_a.py")
    assert TestSelectionResult(selected_tests=[candidate]).selected_tests == [candidate]
    assert TestSelectionResult().selected_tests == []


def test_cli_main_prints_name(capsys) -> None:
    assert main([]) == 0
    assert "Change-Aware Testing Agent" in capsys.readouterr().out


def test_cli_module_runs() -> None:
    src = Path(__file__).resolve().parent.parent / "src"
    completed = subprocess.run(
        [sys.executable, "-m", "change_aware"],
        capture_output=True,
        text=True,
        env={**os.environ, "PYTHONPATH": str(src)},
    )
    assert completed.returncode == 0
    assert "Change-Aware Testing Agent" in completed.stdout
