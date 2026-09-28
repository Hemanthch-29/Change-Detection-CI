from dataclasses import dataclass, field
from enum import Enum


class ChangeType(str, Enum):
    ADDED = "ADDED"
    MODIFIED = "MODIFIED"
    DELETED = "DELETED"
    RENAMED = "RENAMED"


@dataclass(frozen=True)
class ChangedFile:
    """A file changed between two revisions.

    ``path`` is the current path, or the removed path for deletions.
    ``old_path`` is None for additions and ``new_path`` is None for deletions.
    """

    path: str
    change_type: ChangeType = ChangeType.MODIFIED
    old_path: str | None = None
    new_path: str | None = None


@dataclass(frozen=True)
class DependencyNode:
    id: str  # repository-relative path with forward slashes


@dataclass(frozen=True)
class DependencyEdge:
    source: str  # depends on target
    target: str


@dataclass(frozen=True)
class ImpactedComponent:
    path: str  # repository-relative, forward slashes
    depth: int = 0  # 0 = directly changed, n = n dependency hops from a changed file
    directly_changed: bool = False
    reason: str = ""


@dataclass(frozen=True)
class ImpactAnalysisResult:
    changed_components: list[str] = field(default_factory=list)
    impacted_components: list[ImpactedComponent] = field(default_factory=list)

    @property
    def max_impact_depth(self) -> int:
        return max((c.depth for c in self.impacted_components), default=0)

    @property
    def total_impacted(self) -> int:
        return len(self.impacted_components)


@dataclass(frozen=True)
class TestCandidate:
    __test__ = False  # prevent pytest from collecting this class

    path: str  # repository-relative test file
    selected: bool = False
    reasons: tuple[str, ...] = ()
    impacted_by: tuple[str, ...] = ()  # impacted components responsible for selection

    @property
    def reason(self) -> str:
        return self.reasons[0] if self.reasons else ""


@dataclass(frozen=True)
class TestSelectionResult:
    __test__ = False  # prevent pytest from collecting this class

    selected_tests: list[TestCandidate] = field(default_factory=list)
    skipped_tests: list[TestCandidate] = field(default_factory=list)

    @property
    def discovered_tests(self) -> list[TestCandidate]:
        return sorted(self.selected_tests + self.skipped_tests, key=lambda t: t.path)

    @property
    def selected_paths(self) -> list[str]:
        return [t.path for t in self.selected_tests]

    @property
    def total_tests(self) -> int:
        return len(self.selected_tests) + len(self.skipped_tests)

    @property
    def selected_count(self) -> int:
        return len(self.selected_tests)

    @property
    def skipped_count(self) -> int:
        return len(self.skipped_tests)

    @property
    def reduction_percentage(self) -> float:
        if self.total_tests == 0:
            return 0.0
        return self.skipped_count / self.total_tests * 100
