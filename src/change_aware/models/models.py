from dataclasses import dataclass, field


@dataclass
class ChangedFile:
    path: str


@dataclass
class DependencyNode:
    id: str


@dataclass
class DependencyEdge:
    source: str
    target: str


@dataclass
class ImpactedComponent:
    id: str


@dataclass
class TestCandidate:
    __test__ = False  # prevent pytest from collecting this class

    path: str


@dataclass
class TestSelectionResult:
    __test__ = False  # prevent pytest from collecting this class

    selected_tests: list[TestCandidate] = field(default_factory=list)
