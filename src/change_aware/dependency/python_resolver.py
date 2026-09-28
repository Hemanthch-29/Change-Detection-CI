"""Resolve Python imports to files inside a repository.

Deliberately simple: modules are looked up under a few candidate roots
instead of emulating the full Python import system.
"""

from __future__ import annotations

from collections.abc import Sequence
from pathlib import Path

from change_aware.dependency.analyzer import IGNORED_DIRECTORIES


class PythonModuleResolver:
    def __init__(self, repository_path: Path) -> None:
        self.repository_path = repository_path.resolve()

    def resolve_import(self, module: str | None, level: int, importing_file: Path) -> Path | None:
        """Resolve ``import a.b.c`` / ``from ..a.b import x`` to the most specific local module."""
        bases = self._bases(importing_file, level)
        if module is None:
            return next((f for b in bases if (f := self._local_file(b / "__init__.py"))), None)
        parts = module.split(".")
        for base in bases:
            for end in range(len(parts), 0, -1):
                found = self._module_file(base.joinpath(*parts[:end]))
                if found is not None:
                    return found
        return None

    def resolve_from_import(
        self, module: str | None, names: Sequence[str], level: int, importing_file: Path
    ) -> list[Path]:
        """Resolve ``from module import names``; names that are submodules win over the package."""
        prefix = module.split(".") if module else []
        submodules: list[Path] = []
        for name in names:
            for base in self._bases(importing_file, level):
                found = self._module_file(base.joinpath(*prefix, name))
                if found is not None:
                    submodules.append(found)
                    break
        if submodules:
            return submodules
        package = self.resolve_import(module, level, importing_file)
        return [package] if package is not None else []

    def _bases(self, importing_file: Path, level: int) -> list[Path]:
        current_dir = importing_file.resolve().parent
        if level > 0:
            base = current_dir
            for _ in range(level - 1):
                base = base.parent
            return [base] if self._inside_repository(base) else []

        # Parent of the importing file's top-level package, then src/, then the repo root.
        top = current_dir
        while (top / "__init__.py").is_file() and self._inside_repository(top.parent):
            top = top.parent
        roots: list[Path] = []
        for root in (top, self.repository_path / "src", self.repository_path):
            if root.is_dir() and root not in roots:
                roots.append(root)
        return roots

    def _module_file(self, base: Path) -> Path | None:
        return self._local_file(base.with_name(base.name + ".py")) or self._local_file(
            base / "__init__.py"
        )

    def _local_file(self, candidate: Path) -> Path | None:
        if not candidate.is_file():
            return None
        resolved = candidate.resolve()
        if not self._inside_repository(resolved):
            return None
        relative_parts = resolved.relative_to(self.repository_path).parts
        if any(part in IGNORED_DIRECTORIES for part in relative_parts):
            return None
        return resolved

    def _inside_repository(self, path: Path) -> bool:
        return path == self.repository_path or self.repository_path in path.parents
