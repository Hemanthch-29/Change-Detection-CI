"""Language-independent directed dependency graph. ``A -> B`` means A depends on B."""

from __future__ import annotations

from collections import deque

from change_aware.models import DependencyEdge, DependencyNode


class DependencyGraph:
    def __init__(self) -> None:
        self._nodes: dict[str, DependencyNode] = {}
        self._dependencies: dict[str, set[str]] = {}
        self._dependents: dict[str, set[str]] = {}

    def add_node(self, node: DependencyNode | str) -> DependencyNode:
        if isinstance(node, str):
            node = DependencyNode(id=node)
        existing = self._nodes.get(node.id)
        if existing is not None:
            return existing
        self._nodes[node.id] = node
        self._dependencies[node.id] = set()
        self._dependents[node.id] = set()
        return node

    def add_dependency(self, source: str, target: str) -> None:
        """Record that ``source`` depends on ``target``. Missing nodes are created."""
        self.add_node(source)
        self.add_node(target)
        self._dependencies[source].add(target)
        self._dependents[target].add(source)

    def contains(self, node: str) -> bool:
        return node in self._nodes

    def nodes(self) -> list[DependencyNode]:
        return [self._nodes[key] for key in sorted(self._nodes)]

    def edges(self) -> list[DependencyEdge]:
        return [
            DependencyEdge(source=source, target=target)
            for source in sorted(self._dependencies)
            for target in sorted(self._dependencies[source])
        ]

    def get_dependencies(self, node: str) -> list[str]:
        return sorted(self._dependencies.get(node, ()))

    def get_dependents(self, node: str) -> list[str]:
        return sorted(self._dependents.get(node, ()))

    def traverse_dependencies(self, node: str) -> list[str]:
        """All nodes reachable from ``node`` (excluding itself), in BFS order."""
        return self._traverse(node, self._dependencies)

    def traverse_dependents(self, node: str) -> list[str]:
        """All nodes that transitively depend on ``node`` (excluding itself), in BFS order."""
        return self._traverse(node, self._dependents)

    @staticmethod
    def _traverse(start: str, adjacency: dict[str, set[str]]) -> list[str]:
        visited = {start}
        order: list[str] = []
        queue = deque([start])
        while queue:
            current = queue.popleft()
            for neighbor in sorted(adjacency.get(current, ())):
                if neighbor not in visited:
                    visited.add(neighbor)
                    order.append(neighbor)
                    queue.append(neighbor)
        return order
