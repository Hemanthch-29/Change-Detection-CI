import subprocess
from pathlib import Path

import pytest

from change_aware.change_detection import (
    ChangeDetector,
    CommitNotFoundError,
    GitCommandError,
    NotAGitRepositoryError,
    RepositoryNotFoundError,
)
from change_aware.cli import main
from change_aware.models import ChangedFile, ChangeType


def _git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True, text=True
    ).stdout.strip()


def _write(repo: Path, rel: str, content: str) -> None:
    file = repo / rel
    file.parent.mkdir(parents=True, exist_ok=True)
    file.write_text(content, encoding="utf-8")


def _commit(repo: Path, message: str) -> str:
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "--allow-empty", "-m", message)
    return _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # Keep git from discovering a parent repository above tmp_path.
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    path = tmp_path / "repo"
    path.mkdir()
    _git(path, "init", "-q")
    _git(path, "config", "user.name", "Test")
    _git(path, "config", "user.email", "test@example.com")
    _git(path, "config", "commit.gpgsign", "false")
    _git(path, "config", "core.autocrlf", "false")
    _write(path, "src/payment/service.py", "def pay():\n    return 1\n")
    _write(path, "src/old.py", "OLD = True\n")
    return path


def test_modified_file(repo: Path) -> None:
    base = _commit(repo, "base")
    _write(repo, "src/payment/service.py", "def pay():\n    return 2\n")
    head = _commit(repo, "modify")

    assert ChangeDetector(repo).detect(base, head) == [
        ChangedFile(
            "src/payment/service.py",
            ChangeType.MODIFIED,
            old_path="src/payment/service.py",
            new_path="src/payment/service.py",
        )
    ]


def test_added_file(repo: Path) -> None:
    base = _commit(repo, "base")
    _write(repo, "src/payment/tax.py", "RATE = 0.2\n")
    head = _commit(repo, "add")

    assert ChangeDetector(repo).detect(base, head) == [
        ChangedFile("src/payment/tax.py", ChangeType.ADDED, new_path="src/payment/tax.py")
    ]


def test_deleted_file(repo: Path) -> None:
    base = _commit(repo, "base")
    (repo / "src/old.py").unlink()
    head = _commit(repo, "delete")

    assert ChangeDetector(repo).detect(base, head) == [
        ChangedFile("src/old.py", ChangeType.DELETED, old_path="src/old.py")
    ]


def test_renamed_file(repo: Path) -> None:
    base = _commit(repo, "base")
    (repo / "src/legacy").mkdir()
    (repo / "src/old.py").rename(repo / "src/legacy/renamed.py")
    head = _commit(repo, "rename")

    assert ChangeDetector(repo).detect(base, head) == [
        ChangedFile(
            "src/legacy/renamed.py",
            ChangeType.RENAMED,
            old_path="src/old.py",
            new_path="src/legacy/renamed.py",
        )
    ]


def test_multiple_changed_files(repo: Path) -> None:
    base = _commit(repo, "base")
    _write(repo, "src/payment/service.py", "def pay():\n    return 3\n")
    _write(repo, "src/payment/tax.py", "RATE = 0.2\n")
    (repo / "src/old.py").unlink()
    head = _commit(repo, "multiple")

    changes = ChangeDetector(repo).detect(base, head)
    assert {(c.change_type, c.path) for c in changes} == {
        (ChangeType.MODIFIED, "src/payment/service.py"),
        (ChangeType.ADDED, "src/payment/tax.py"),
        (ChangeType.DELETED, "src/old.py"),
    }
    assert all("\\" not in c.path and not Path(c.path).is_absolute() for c in changes)


def test_no_changes(repo: Path) -> None:
    base = _commit(repo, "base")
    head = _commit(repo, "empty")

    assert ChangeDetector(repo).detect(base, head) == []
    assert ChangeDetector(repo).detect(base, base) == []


def test_symbolic_refs_are_accepted(repo: Path) -> None:
    _commit(repo, "base")
    _write(repo, "src/payment/tax.py", "RATE = 0.2\n")
    _commit(repo, "add")

    assert [c.path for c in ChangeDetector(repo).detect("HEAD~1", "HEAD")] == ["src/payment/tax.py"]


def test_repository_path_does_not_exist(tmp_path: Path) -> None:
    with pytest.raises(RepositoryNotFoundError):
        ChangeDetector(tmp_path / "missing")


def test_path_is_not_a_git_repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("GIT_CEILING_DIRECTORIES", str(tmp_path))
    plain = tmp_path / "plain"
    plain.mkdir()
    with pytest.raises(NotAGitRepositoryError):
        ChangeDetector(plain)


@pytest.mark.parametrize("which", ["base", "head"])
def test_invalid_commit(repo: Path, which: str) -> None:
    good = _commit(repo, "base")
    base, head = ("doesnotexist", good) if which == "base" else (good, "doesnotexist")

    with pytest.raises(CommitNotFoundError) as exc_info:
        ChangeDetector(repo).detect(base, head)
    assert exc_info.value.commit == "doesnotexist"


def test_option_like_commit_is_rejected(repo: Path) -> None:
    good = _commit(repo, "base")
    with pytest.raises(CommitNotFoundError):
        ChangeDetector(repo).detect("--output=pwned.txt", good)
    assert not (repo / "pwned.txt").exists()


def test_git_command_failure_is_wrapped(repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    detector = ChangeDetector(repo)

    def fail(*args: object, **kwargs: object) -> None:
        raise FileNotFoundError("git not found")

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(GitCommandError):
        detector.detect("HEAD", "HEAD")


def test_cli_detect_changes(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base = _commit(repo, "base")
    _write(repo, "src/payment/tax.py", "RATE = 0.2\n")
    head = _commit(repo, "add")

    assert main(["detect-changes", str(repo), base, head]) == 0
    assert capsys.readouterr().out == "Changed files:\n  ADDED     src/payment/tax.py\n"


def test_cli_no_changes(repo: Path, capsys: pytest.CaptureFixture[str]) -> None:
    base = _commit(repo, "base")

    assert main(["detect-changes", str(repo), base, base]) == 0
    assert capsys.readouterr().out == "No files changed.\n"


def test_cli_reports_errors(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["detect-changes", str(tmp_path / "missing"), "a", "b"]) == 1
    assert "Error:" in capsys.readouterr().err
