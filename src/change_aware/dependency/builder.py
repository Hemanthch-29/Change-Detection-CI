"""Scan a repository and build a ``DependencyGraph`` using language analyzers."""

from __future__ import annotations

import logging
import os
from collections.abc import Sequence
from pathlib import Path

from change_aware.dependency.analyzer import IGNORED_DIRECTORIES, LanguageAnalyzer
from change_aware.dependency.graph import DependencyGraph
from change_aware.dependency.python_analyzer import PythonAnalyzer

logger = logging.getLogger(__name__)


class DependencyAnalysisError(Exception):
    pass


class DependencyGraphBuilder:
    def __init__(self, analyzers: Sequence[LanguageAnalyzer] | None = None) -> None:
        self.analyzers: list[LanguageAnalyzer] = (
            list(analyzers) if analyzers is not None else [PythonAnalyzer()]
        )

    def build(self, repository_path: str | Path) -> DependencyGraph:
        repo = Path(repository_path)
        if not repo.is_dir():
            raise DependencyAnalysisError(f"Repository path does not exist: {repo}")
        repo = repo.resolve()

        graph = DependencyGraph()
        scanned = skipped = 0
        for file_path in iter_repository_files(repo):
            analyzer = next((a for a in self.analyzers if a.supports(file_path)), None)
            if analyzer is None:
                skipped += 1
                continue
            scanned += 1
            graph.add_node(file_path.relative_to(repo).as_posix())
            for edge in analyzer.analyze(file_path, repo):
                graph.add_dependency(edge.source, edge.target)

        logger.info("Scanned %d file(s), skipped %d; graph has %d node(s) and %d edge(s)",
                    scanned, skipped, len(graph.nodes()), len(graph.edges()))
        return graph


def iter_repository_files(repo: Path) -> list[Path]:
    """All files under ``repo`` in sorted order, skipping ``IGNORED_DIRECTORIES``."""
    files: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(repo):
        pruned = [d for d in dirnames if d in IGNORED_DIRECTORIES]
        if pruned:
            logger.debug("Ignoring directories in %s: %s", dirpath, ", ".join(pruned))
        dirnames[:] = sorted(d for d in dirnames if d not in IGNORED_DIRECTORIES)
        files.extend(Path(dirpath) / name for name in sorted(filenames))
    return files
