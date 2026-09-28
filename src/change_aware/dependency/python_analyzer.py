"""Python dependency analysis using the standard-library ``ast`` module."""

from __future__ import annotations

import ast
import logging
from dataclasses import dataclass
from pathlib import Path

from change_aware.dependency.analyzer import LanguageAnalyzer
from change_aware.dependency.python_resolver import PythonModuleResolver
from change_aware.models import DependencyEdge

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ImportReference:
    module: str | None  # None for "from . import x"
    names: tuple[str, ...] = ()
    level: int = 0  # 0 = absolute import


def extract_imports(source: str | bytes, filename: str = "<unknown>") -> list[ImportReference]:
    """Parse source and return every import statement. Raises SyntaxError on invalid code."""
    tree = ast.parse(source, filename=filename)
    refs: list[ImportReference] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            refs.extend(ImportReference(module=alias.name) for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            names = tuple(alias.name for alias in node.names if alias.name != "*")
            refs.append(ImportReference(module=node.module, names=names, level=node.level))
    return refs


class PythonAnalyzer(LanguageAnalyzer):
    def __init__(self) -> None:
        self._resolvers: dict[Path, PythonModuleResolver] = {}

    def supports(self, file_path: Path) -> bool:
        return file_path.suffix == ".py"

    def analyze(self, file_path: Path, repository_path: Path) -> list[DependencyEdge]:
        repo = repository_path.resolve()
        file_path = file_path.resolve()
        source_id = file_path.relative_to(repo).as_posix()

        try:
            imports = extract_imports(file_path.read_bytes(), filename=source_id)
        except (SyntaxError, ValueError) as exc:
            logger.warning("Skipping %s: cannot parse Python source (%s)", source_id, exc)
            return []
        except OSError as exc:
            logger.warning("Skipping %s: cannot read file (%s)", source_id, exc)
            return []

        resolver = self._resolvers.setdefault(repo, PythonModuleResolver(repo))
        targets: set[str] = set()
        for ref in imports:
            for target in self._resolve(ref, file_path, resolver):
                target_id = target.relative_to(repo).as_posix()
                if target_id != source_id:
                    targets.add(target_id)

        logger.debug("%s: %d import(s), %d local dependency(ies)",
                     source_id, len(imports), len(targets))
        return [DependencyEdge(source=source_id, target=t) for t in sorted(targets)]

    @staticmethod
    def _resolve(
        ref: ImportReference, file_path: Path, resolver: PythonModuleResolver
    ) -> list[Path]:
        if ref.names or ref.module is None:
            targets = resolver.resolve_from_import(ref.module, ref.names, ref.level, file_path)
        else:
            found = resolver.resolve_import(ref.module, ref.level, file_path)
            targets = [found] if found is not None else []

        if not targets:
            label = "." * ref.level + (ref.module or "")
            if ref.level > 0:
                logger.info("Unresolved relative import %r in %s", label, file_path.name)
            else:
                logger.debug("Import %r in %s is not local; ignoring", label, file_path.name)
        return targets
