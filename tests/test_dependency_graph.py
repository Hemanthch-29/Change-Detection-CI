import logging
from pathlib import Path

import pytest

from change_aware.cli import main
from change_aware.dependency import (
    DependencyAnalysisError,
    DependencyGraph,
    DependencyGraphBuilder,
    PythonAnalyzer,
)
from change_aware.models import DependencyEdge, DependencyNode


def _write(root: Path, files: dict[str, str]) -> Path:
    for rel, content in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    return root


def _edges(repo: Path, rel: str) -> list[str]:
    return [e.target for e in PythonAnalyzer().analyze(repo / rel, repo)]


def _chain() -> DependencyGraph:
    graph = DependencyGraph()
    graph.add_dependency("a.py", "b.py")
    graph.add_dependency("b.py", "c.py")
    return graph


# --- DependencyGraph -------------------------------------------------------


def test_add_nodes() -> None:
    graph = DependencyGraph()
    graph.add_node("a.py")
    graph.add_node(DependencyNode(id="b.py"))
    graph.add_node("a.py")

    assert graph.nodes() == [DependencyNode("a.py"), DependencyNode("b.py")]
    assert graph.contains("a.py")
    assert not graph.contains("missing.py")
    assert graph.edges() == []


def test_add_dependency_creates_nodes_and_edge() -> None:
    graph = DependencyGraph()
    graph.add_dependency("a.py", "b.py")

    assert graph.contains("a.py") and graph.contains("b.py")
    assert graph.edges() == [DependencyEdge("a.py", "b.py")]


def test_get_dependencies_and_dependents() -> None:
    graph = _chain()
    assert graph.get_dependencies("a.py") == ["b.py"]
    assert graph.get_dependencies("c.py") == []
    assert graph.get_dependents("c.py") == ["b.py"]
    assert graph.get_dependents("a.py") == []
    assert graph.get_dependencies("unknown.py") == []


def test_traverse_dependencies() -> None:
    assert _chain().traverse_dependencies("a.py") == ["b.py", "c.py"]


def test_traverse_dependents() -> None:
    assert _chain().traverse_dependents("c.py") == ["b.py", "a.py"]


def test_circular_dependencies_terminate() -> None:
    graph = _chain()
    graph.add_dependency("c.py", "a.py")

    assert graph.traverse_dependencies("a.py") == ["b.py", "c.py"]
    assert graph.traverse_dependents("a.py") == ["c.py", "b.py"]


def test_duplicate_edges_are_ignored() -> None:
    graph = DependencyGraph()
    graph.add_dependency("a.py", "b.py")
    graph.add_dependency("a.py", "b.py")

    assert graph.edges() == [DependencyEdge("a.py", "b.py")]
    assert graph.get_dependents("b.py") == ["a.py"]


def test_traversal_is_deterministic() -> None:
    graph = DependencyGraph()
    for target in ("z.py", "m.py", "b.py"):
        graph.add_dependency("root.py", target)
    graph.add_dependency("b.py", "leaf.py")

    assert graph.traverse_dependencies("root.py") == ["b.py", "m.py", "z.py", "leaf.py"]


# --- PythonAnalyzer --------------------------------------------------------


def test_import_statement(tmp_path: Path) -> None:
    repo = _write(tmp_path, {
        "payment/__init__.py": "",
        "payment/service.py": "",
        "app.py": "import payment.service\n",
    })
    assert _edges(repo, "app.py") == ["payment/service.py"]


def test_from_import(tmp_path: Path) -> None:
    repo = _write(tmp_path, {
        "payment/__init__.py": "",
        "payment/service.py": "def calculate_total(): ...\n",
        "payment/controller.py": "from payment.service import calculate_total\n",
    })
    assert _edges(repo, "payment/controller.py") == ["payment/service.py"]


def test_from_package_import_submodule(tmp_path: Path) -> None:
    repo = _write(tmp_path, {
        "payment/__init__.py": "",
        "payment/service.py": "",
        "payment/tax.py": "",
        "app.py": "from payment import service, tax\nfrom payment import something_else\n",
    })
    assert _edges(repo, "app.py") == ["payment/__init__.py", "payment/service.py", "payment/tax.py"]


def test_relative_import(tmp_path: Path) -> None:
    repo = _write(tmp_path, {
        "payment/__init__.py": "",
        "payment/service.py": "",
        "payment/controller.py": "from .service import calculate_total\nfrom . import service\n",
    })
    assert _edges(repo, "payment/controller.py") == ["payment/service.py"]


def test_parent_relative_import(tmp_path: Path) -> None:
    repo = _write(tmp_path, {
        "shop/__init__.py": "",
        "shop/common.py": "",
        "shop/payment/__init__.py": "",
        "shop/payment/controller.py": "from ..common import helper\n",
    })
    assert _edges(repo, "shop/payment/controller.py") == ["shop/common.py"]


def test_src_layout(tmp_path: Path) -> None:
    repo = _write(tmp_path, {
        "src/payment/__init__.py": "",
        "src/payment/service.py": "",
        "src/payment/controller.py": "from payment.service import calculate_total\n",
        "tests/test_service.py": "from payment.service import calculate_total\n",
    })
    assert _edges(repo, "src/payment/controller.py") == ["src/payment/service.py"]
    assert _edges(repo, "tests/test_service.py") == ["src/payment/service.py"]


def test_external_dependencies_are_ignored(tmp_path: Path) -> None:
    repo = _write(tmp_path, {
        "app.py": "import os\nimport json.decoder\nfrom collections import deque\n"
                  "import requests\nfrom numpy import array\nimport local_mod\n",
        "local_mod.py": "",
        ".venv/lib/site-packages/requests/__init__.py": "",
    })
    assert _edges(repo, "app.py") == ["local_mod.py"]


def test_duplicate_imports_produce_one_edge(tmp_path: Path) -> None:
    repo = _write(tmp_path, {
        "util.py": "",
        "app.py": "import util\nimport util\nfrom util import a\ndef f():\n    import util\n",
    })
    assert _edges(repo, "app.py") == ["util.py"]


# --- DependencyGraphBuilder ------------------------------------------------


def test_invalid_python_is_skipped_and_build_continues(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    repo = _write(tmp_path, {
        "broken.py": "def oops(:\n",
        "service.py": "",
        "controller.py": "import service\n",
    })
    with caplog.at_level(logging.WARNING):
        graph = DependencyGraphBuilder().build(repo)

    assert graph.contains("broken.py")
    assert graph.get_dependencies("broken.py") == []
    assert graph.get_dependencies("controller.py") == ["service.py"]
    assert any("broken.py" in r.message for r in caplog.records)


def test_build_graph_from_repository(tmp_path: Path) -> None:
    repo = _write(tmp_path, {
        "payment/__init__.py": "",
        "payment/service.py": "import os\n",
        "payment/controller.py": "from payment.service import calculate_total\n",
        "checkout/__init__.py": "",
        "checkout/service.py": "from payment import service\nfrom ..outside import x\n",
        "README.md": "not python",
        ".git/hooks/hook.py": "import payment.service\n",
        "pkg/__pycache__/cached.py": "import payment.service\n",
        "venv/lib/mod.py": "import payment.service\n",
        ".venv/lib/mod.py": "import payment.service\n",
        "lib/site-packages/mod.py": "import payment.service\n",
    })
    graph = DependencyGraphBuilder().build(repo)

    assert [n.id for n in graph.nodes()] == [
        "checkout/__init__.py",
        "checkout/service.py",
        "payment/__init__.py",
        "payment/controller.py",
        "payment/service.py",
    ]
    assert graph.edges() == [
        DependencyEdge("checkout/service.py", "payment/service.py"),
        DependencyEdge("payment/controller.py", "payment/service.py"),
    ]
    assert graph.traverse_dependents("payment/service.py") == [
        "checkout/service.py",
        "payment/controller.py",
    ]


def test_build_missing_repository_raises(tmp_path: Path) -> None:
    with pytest.raises(DependencyAnalysisError):
        DependencyGraphBuilder().build(tmp_path / "missing")


def test_cli_build_graph(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    repo = _write(tmp_path, {"service.py": "", "controller.py": "import service\n"})

    assert main(["build-graph", str(repo)]) == 0
    assert capsys.readouterr().out == (
        "Dependency Graph\n"
        "================\n"
        "\n"
        "controller.py\n"
        "  -> service.py\n"
        "\n"
        "service.py\n"
        "  (no local dependencies)\n"
        "\n"
        "2 node(s), 1 edge(s)\n"
    )
