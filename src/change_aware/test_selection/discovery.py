"""Discover pytest-style test files in a repository without executing them."""

from __future__ import annotations

import fnmatch
import logging
from pathlib import Path

from change_aware.dependency import iter_repository_files

logger = logging.getLogger(__name__)

TEST_FILE_PATTERNS = ("test_*.py", "*_test.py")


def is_test_file(path: str | Path) -> bool:
    name = Path(path).name
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in TEST_FILE_PATTERNS)


class TestDiscovery:
    __test__ = False  # prevent pytest from collecting this class

    def discover(self, repository_path: str | Path) -> list[str]:
        """Return repository-relative test file paths (forward slashes), sorted."""
        repo = Path(repository_path).resolve()
        tests = sorted(
            path.relative_to(repo).as_posix()
            for path in iter_repository_files(repo)
            if is_test_file(path)
        )
        logger.info("Discovered %d test file(s) in %s", len(tests), repo)
        return tests
