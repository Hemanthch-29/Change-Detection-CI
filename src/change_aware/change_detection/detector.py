"""Git-based change detection. All Git-specific behavior lives in this package."""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path

from change_aware.models import ChangedFile, ChangeType

logger = logging.getLogger(__name__)


class ChangeDetectionError(Exception):
    """Base class for all change detection errors."""


class RepositoryNotFoundError(ChangeDetectionError):
    pass


class NotAGitRepositoryError(ChangeDetectionError):
    pass


class CommitNotFoundError(ChangeDetectionError):
    def __init__(self, commit: str) -> None:
        super().__init__(f"Commit not found: {commit!r}")
        self.commit = commit


class GitCommandError(ChangeDetectionError):
    def __init__(self, message: str, returncode: int | None = None) -> None:
        super().__init__(message)
        self.returncode = returncode  # None when git could not be executed at all


class ChangeDetector:
    """Detects files changed between two commits of a local Git repository."""

    def __init__(self, repository_path: str | Path) -> None:
        path = Path(repository_path)
        if not path.is_dir():
            raise RepositoryNotFoundError(f"Repository path does not exist: {path}")
        try:
            toplevel = _run_git(["rev-parse", "--show-toplevel"], cwd=path)
        except GitCommandError as exc:
            if exc.returncode is None:
                raise
            raise NotAGitRepositoryError(f"Not a Git repository: {path}") from exc
        self.repository_path = Path(toplevel.strip())
        logger.debug("Using Git repository at %s", self.repository_path)

    def detect(self, base_commit: str, head_commit: str) -> list[ChangedFile]:
        base_sha = self._resolve_commit(base_commit)
        head_sha = self._resolve_commit(head_commit)
        logger.debug("Diffing %s (%s) -> %s (%s)", base_commit, base_sha, head_commit, head_sha)

        output = _run_git(
            ["diff", "--name-status", "-z", "-M", "--no-color", "--no-ext-diff", base_sha, head_sha],
            cwd=self.repository_path,
        )
        changes = parse_name_status_z(output)
        logger.info("Detected %d changed file(s) between %s and %s",
                    len(changes), base_commit, head_commit)
        return changes

    def _resolve_commit(self, commit: str) -> str:
        try:
            # --end-of-options stops a ref like "--foo" from being parsed as an option
            return _run_git(
                ["rev-parse", "--verify", "--quiet", "--end-of-options", f"{commit}^{{commit}}"],
                cwd=self.repository_path,
            ).strip()
        except GitCommandError as exc:
            if exc.returncode is None:
                raise
            raise CommitNotFoundError(commit) from exc


def parse_name_status_z(output: str) -> list[ChangedFile]:
    """Parse ``git diff --name-status -z`` output."""
    tokens = [t for t in output.split("\0") if t]
    changes: list[ChangedFile] = []
    i = 0
    while i < len(tokens):
        status = tokens[i][0]
        if status in ("R", "C"):
            old, new = _normalize(tokens[i + 1]), _normalize(tokens[i + 2])
            i += 3
            if status == "R":
                changes.append(ChangedFile(new, ChangeType.RENAMED, old_path=old, new_path=new))
            else:
                changes.append(ChangedFile(new, ChangeType.ADDED, new_path=new))
            continue

        path = _normalize(tokens[i + 1])
        i += 2
        if status == "A":
            changes.append(ChangedFile(path, ChangeType.ADDED, new_path=path))
        elif status == "D":
            changes.append(ChangedFile(path, ChangeType.DELETED, old_path=path))
        else:
            # M, T (type change) and anything else are treated as modifications
            changes.append(ChangedFile(path, ChangeType.MODIFIED, old_path=path, new_path=path))
    return changes


def _normalize(path: str) -> str:
    return path.replace("\\", "/")


def _run_git(args: list[str], cwd: Path) -> str:
    cmd = ["git", *args]
    logger.debug("Running %s in %s", " ".join(cmd), cwd)
    try:
        completed = subprocess.run(
            cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace"
        )
    except OSError as exc:
        raise GitCommandError(f"Failed to execute git: {exc}") from exc
    if completed.returncode != 0:
        stderr = completed.stderr.strip()
        logger.debug("git exited with %d: %s", completed.returncode, stderr)
        raise GitCommandError(
            f"git {args[0]} failed with exit code {completed.returncode}: {stderr}",
            returncode=completed.returncode,
        )
    return completed.stdout
