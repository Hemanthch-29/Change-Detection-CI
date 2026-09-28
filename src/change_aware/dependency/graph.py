from change_aware.models import DependencyEdge, DependencyNode


class DependencyGraph:
    def __init__(self) -> None:
        self.nodes: list[DependencyNode] = []
        self.edges: list[DependencyEdge] = []
