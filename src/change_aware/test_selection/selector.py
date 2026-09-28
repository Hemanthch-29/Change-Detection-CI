"""Select tests relevant to impacted components. Deterministic and explainable; never runs tests."""

from __future__ import annotations

import logging
from pathlib import Path, PurePosixPath

from change_aware.dependency import PythonAnalyzer
from change_aware.models import ImpactAnalysisResult, ImpactedComponent, TestCandidate, TestSelectionResult
from change_aware.test_selection.discovery import TestDiscovery

logger = logging.getLogger(__name__)

REASON_CHANGED_TEST = "test file was directly changed"
REASON_DIRECT_IMPORT = "test imports impacted component"
REASON_TRANSITIVE_IMPORT = "test imports transitively impacted component"
REASON_NAMING = "test matches impacted component by naming convention"
# Reasons are listed on a candidate in this order.
_REASON_ORDER = (REASON_CHANGED_TEST, REASON_DIRECT_IMPORT, REASON_TRANSITIVE_IMPORT, REASON_NAMING)

_SOURCE_ROOTS = {"src"}
_TEST_DIRS = {"tests", "test"}


class TestSelectionError(Exception):
    __test__ = False  # prevent pytest from collecting this class


class TestSelector:
    __test__ = False  # prevent pytest from collecting this class

    def __init__(
        self, discovery: TestDiscovery | None = None, import_analyzer: PythonAnalyzer | None = None
    ) -> None:
        self.discovery = discovery or TestDiscovery()
        self.import_analyzer = import_analyzer or PythonAnalyzer()

    def select(
        self, repository_path: str | Path, impact: ImpactAnalysisResult
    ) -> TestSelectionResult:
        repo = Path(repository_path)
        if not repo.is_dir():
            raise TestSelectionError(f"Repository path does not exist: {repo}")
        repo = repo.resolve()

        impacted = {c.path: c for c in impact.impacted_components}
        # Map each naming-convention key to the impacted source files that produce it.
        by_name: dict[tuple[str, ...], list[ImpactedComponent]] = {}
        for component in impacted.values():
            for key in source_naming_keys(component.path):
                by_name.setdefault(key, []).append(component)

        selected: list[tuple[int, TestCandidate]] = []
        skipped: list[TestCandidate] = []
        for test_path in self.discovery.discover(repo):
            reasons: dict[str, set[str]] = {}

            own = impacted.get(test_path)
            if own is not None and own.directly_changed:
                reasons.setdefault(REASON_CHANGED_TEST, set()).add(test_path)

            for edge in self.import_analyzer.analyze(repo / test_path, repo):
                component = impacted.get(edge.target)
                if component is not None:
                    reason = REASON_DIRECT_IMPORT if component.depth == 0 else REASON_TRANSITIVE_IMPORT
                    reasons.setdefault(reason, set()).add(component.path)

            key = naming_key_for_test(test_path)
            for component in by_name.get(key, []) if key else []:
                if component.path != test_path:
                    reasons.setdefault(REASON_NAMING, set()).add(component.path)

            if not reasons:
                skipped.append(TestCandidate(path=test_path))
                continue

            responsible = sorted(set().union(*reasons.values()))
            candidate = TestCandidate(
                path=test_path,
                selected=True,
                reasons=tuple(r for r in _REASON_ORDER if r in reasons),
                impacted_by=tuple(responsible),
            )
            closest = min(impacted[p].depth for p in responsible)
            logger.debug("Selected %s: %s", test_path, "; ".join(candidate.reasons))
            selected.append((closest, candidate))

        selected.sort(key=lambda item: (item[0], item[1].path))
        result = TestSelectionResult(
            selected_tests=[candidate for _, candidate in selected],
            skipped_tests=skipped,
        )
        logger.info("Selected %d of %d test file(s) (%.1f%% reduction)",
                    result.selected_count, result.total_tests, result.reduction_percentage)
        return result


def source_naming_keys(path: str) -> list[tuple[str, ...]]:
    """Keys a source file can be matched by.

    ``src/payment/service.py`` -> ``("payment", "service")`` and flattened ``("payment_service",)``
    """
    pure = PurePosixPath(path)
    if pure.suffix != ".py":
        return []
    parts = list(pure.with_suffix("").parts)
    if parts and parts[0] in _SOURCE_ROOTS:
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    if not parts:
        return []
    keys = [tuple(parts)]
    if len(parts) > 1:
        keys.append(("_".join(parts),))
    return keys


def naming_key_for_test(path: str) -> tuple[str, ...] | None:
    """Key for a test file: ``tests/payment/test_service.py`` -> ``("payment", "service")``."""
    pure = PurePosixPath(path)
    stem = pure.stem
    if stem.startswith("test_"):
        stem = stem[len("test_"):]
    elif stem.endswith("_test"):
        stem = stem[: -len("_test")]
    if not stem:
        return None
    dirs = [d for d in pure.parent.parts if d not in _TEST_DIRS]
    if dirs and dirs[0] in _SOURCE_ROOTS:
        dirs = dirs[1:]
    return (*dirs, stem)
