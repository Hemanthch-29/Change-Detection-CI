"""Impact analysis: which components may be affected by a set of changed files."""

from __future__ import annotations

import logging
from collections.abc import Sequence

from change_aware.dependency import DependencyGraph
from change_aware.models import ChangedFile, ChangeType, ImpactAnalysisResult, ImpactedComponent

logger = logging.getLogger(__name__)


class ImpactAnalyzer:
    """If A depends on B and B changes, A may be impacted (reverse dependency traversal)."""

    def analyze(
        self, changed_files: Sequence[ChangedFile], graph: DependencyGraph
    ) -> ImpactAnalysisResult:
        changes = {c.path: c for c in changed_files}
        changed_paths = sorted(changes)
        impacted: dict[str, ImpactedComponent] = {
            path: ImpactedComponent(
                path=path, depth=0, directly_changed=True, reason=_direct_reason(changes[path])
            )
            for path in changed_paths
        }

        for changed_path in changed_paths:
            if not graph.contains(changed_path):
                logger.debug("%s is not in the dependency graph; no dependents", changed_path)
                continue
            dependents = graph.traverse_dependents_with_depth(changed_path)
            logger.debug("%s has %d transitive dependent(s)", changed_path, len(dependents))
            for path, depth in dependents:
                existing = impacted.get(path)
                # Keep the shortest path; ties go to the first changed file in sorted order.
                if existing is None or depth < existing.depth:
                    relation = "depends on" if depth == 1 else "transitively depends on"
                    impacted[path] = ImpactedComponent(
                        path=path, depth=depth, reason=f"{relation} {changed_path}"
                    )

        result = ImpactAnalysisResult(
            changed_components=changed_paths,
            impacted_components=sorted(impacted.values(), key=lambda c: (c.depth, c.path)),
        )
        logger.info("Impact analysis: %d changed, %d impacted, max depth %d",
                    len(changed_paths), result.total_impacted, result.max_impact_depth)
        return result


def _direct_reason(change: ChangedFile) -> str:
    if change.change_type is ChangeType.RENAMED and change.old_path:
        return f"renamed from {change.old_path}"
    return change.change_type.value.lower()
