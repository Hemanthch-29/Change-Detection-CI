"""Abstraction for per-language dependency analyzers."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from change_aware.models import DependencyEdge

IGNORED_DIRECTORIES = frozenset({".git", "__pycache__", ".venv", "venv", "site-packages"})


class LanguageAnalyzer(ABC):
    @abstractmethod
    def supports(self, file_path: Path) -> bool:
        """Return True if this analyzer handles ``file_path``."""

    @abstractmethod
    def analyze(self, file_path: Path, repository_path: Path) -> list[DependencyEdge]:
        """Return edges from ``file_path`` to local files it depends on.

        Edge endpoints are repository-relative paths with forward slashes.
        """
