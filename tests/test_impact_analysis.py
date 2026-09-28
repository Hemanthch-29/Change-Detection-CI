import random

from change_aware.dependency import DependencyGraph
from change_aware.impact import ImpactAnalyzer
from change_aware.models import ChangedFile, ChangeType, ImpactAnalysisResult, ImpactedComponent


def _graph(*edges: tuple[str, str], nodes: tuple[str, ...] = ()) -> DependencyGraph:
    graph = DependencyGraph()
    for node in nodes:
        graph.add_node(node)
    for source, target in edges:
        graph.add_dependency(source, target)
    return graph


def _analyze(graph: DependencyGraph, *paths: str) -> ImpactAnalysisResult:
    return ImpactAnalyzer().analyze([ChangedFile(p) for p in paths], graph)


def _depths(result: ImpactAnalysisResult) -> list[tuple[str, int]]:
    return [(c.path, c.depth) for c in result.impacted_components]


CHAIN = (
    ("checkout/service.py", "payment/service.py"),
    ("payment/service.py", "payment/tax.py"),
)


def test_directly_changed_file() -> None:
    result = _analyze(_graph(nodes=("payment/tax.py",)), "payment/tax.py")

    assert result.changed_components == ["payment/tax.py"]
    assert result.impacted_components == [
        ImpactedComponent("payment/tax.py", depth=0, directly_changed=True, reason="modified")
    ]
    assert result.total_impacted == 1
    assert result.max_impact_depth == 0


def test_one_level_dependency() -> None:
    result = _analyze(_graph(("payment/service.py", "payment/tax.py")), "payment/tax.py")

    assert result.impacted_components[1] == ImpactedComponent(
        "payment/service.py", depth=1, directly_changed=False, reason="depends on payment/tax.py"
    )


def test_multi_level_transitive_dependency() -> None:
    result = _analyze(_graph(*CHAIN), "payment/tax.py")

    assert _depths(result) == [
        ("payment/tax.py", 0),
        ("payment/service.py", 1),
        ("checkout/service.py", 2),
    ]
    assert result.impacted_components[2].reason == "transitively depends on payment/tax.py"
    assert result.max_impact_depth == 2
    assert result.total_impacted == 3


def test_multiple_changed_files_union() -> None:
    graph = _graph(("A", "B"), ("B", "C"), ("X", "Y"))
    result = _analyze(graph, "B", "Y")

    assert result.changed_components == ["B", "Y"]
    assert _depths(result) == [("B", 0), ("Y", 0), ("A", 1), ("X", 1)]


def test_unrelated_files_are_not_impacted() -> None:
    graph = _graph(
        ("payment/controller.py", "payment/service.py"),
        ("user/controller.py", "user/service.py"),
    )
    result = _analyze(graph, "payment/service.py")

    paths = [c.path for c in result.impacted_components]
    assert paths == ["payment/service.py", "payment/controller.py"]
    assert "user/service.py" not in paths


def test_dependencies_of_changed_file_are_not_impacted() -> None:
    # service depends on tax; changing service must not impact tax.
    result = _analyze(_graph(*CHAIN), "payment/service.py")
    assert _depths(result) == [("payment/service.py", 0), ("checkout/service.py", 1)]


def test_circular_dependency_terminates() -> None:
    graph = _graph(("A", "B"), ("B", "C"), ("C", "A"))
    result = _analyze(graph, "A")

    assert _depths(result) == [("A", 0), ("C", 1), ("B", 2)]


def test_duplicate_impact_through_multiple_paths_keeps_shortest() -> None:
    # top reaches base via mid (2 hops) and directly (1 hop).
    graph = _graph(("top", "mid"), ("mid", "base"), ("top", "base"))
    result = _analyze(graph, "base")

    assert _depths(result) == [("base", 0), ("mid", 1), ("top", 1)]


def test_component_impacted_by_several_changes_appears_once() -> None:
    graph = _graph(("app", "a"), ("app", "b"), ("app2", "app"))
    result = _analyze(graph, "a", "b")

    assert _depths(result) == [("a", 0), ("b", 0), ("app", 1), ("app2", 2)]
    assert result.impacted_components[2].reason == "depends on a"


def test_changed_file_that_is_also_dependent_stays_direct() -> None:
    result = _analyze(_graph(*CHAIN), "payment/tax.py", "payment/service.py")

    service = next(c for c in result.impacted_components if c.path == "payment/service.py")
    assert service.depth == 0 and service.directly_changed


def test_no_changed_files() -> None:
    result = _analyze(_graph(*CHAIN))

    assert result.changed_components == []
    assert result.impacted_components == []
    assert result.total_impacted == 0
    assert result.max_impact_depth == 0


def test_changed_file_not_in_graph_is_direct_only() -> None:
    result = _analyze(_graph(*CHAIN), "README.md")
    assert _depths(result) == [("README.md", 0)]


def test_renamed_file_uses_new_path() -> None:
    graph = _graph(("app.py", "pkg/new.py"))
    change = ChangedFile("pkg/new.py", ChangeType.RENAMED, old_path="pkg/old.py", new_path="pkg/new.py")
    result = ImpactAnalyzer().analyze([change], graph)

    assert result.changed_components == ["pkg/new.py"]
    assert result.impacted_components[0].reason == "renamed from pkg/old.py"
    assert _depths(result) == [("pkg/new.py", 0), ("app.py", 1)]


def test_deterministic_ordering() -> None:
    edges = [("z", "base"), ("a", "base"), ("m", "base"), ("deep", "a"), ("deep2", "z")]
    expected = [("base", 0), ("a", 1), ("m", 1), ("z", 1), ("deep", 2), ("deep2", 2)]

    rng = random.Random(0)
    for _ in range(5):
        rng.shuffle(edges)
        assert _depths(_analyze(_graph(*edges), "base")) == expected
