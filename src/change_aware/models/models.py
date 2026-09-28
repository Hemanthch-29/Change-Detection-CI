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
