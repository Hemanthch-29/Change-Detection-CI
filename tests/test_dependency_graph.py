from change_aware.dependency import DependencyGraph


def test_dependency_graph_can_be_instantiated() -> None:
    graph = DependencyGraph()
    assert graph.nodes == []
    assert graph.edges == []
