"""Tests for the Git class."""

import subprocess
import pytest
from pathlib import Path

from gitutils.git import Git


class FakeRunner:
    """Captures subprocess calls for assertion."""

    def __init__(self) -> None:
        self.calls: list[list[str]] = []

    def __call__(self, args: list[str], *, check: bool) -> None:
        assert check is True, "Git commands should always use check=True"
        self.calls.append(args)


@pytest.fixture
def runner() -> FakeRunner:
    return FakeRunner()


# --- clone tests ---


def test_clone_creates_directory_and_runs_git(
    tmp_path: Path, runner: FakeRunner
) -> None:
    repo_dir = tmp_path / "org" / "repo"
    git = Git("https://example.com/repo.git", repo_dir, runner=runner)

    git.clone(with_submodules=False)

    assert repo_dir.exists()
    assert runner.calls == [
        ["git", "clone", "https://example.com/repo.git", str(repo_dir)],
    ]


def test_clone_with_submodules_adds_flags(tmp_path: Path, runner: FakeRunner) -> None:
    repo_dir = tmp_path / "repo"
    git = Git("https://example.com/repo.git", repo_dir, runner=runner)

    git.clone(with_submodules=True)

    assert runner.calls == [
        [
            "git",
            "clone",
            "--recurse-submodules",
            "--remote-submodules",
            "https://example.com/repo.git",
            str(repo_dir),
        ],
    ]


def test_clone_raises_if_directory_exists(tmp_path: Path, runner: FakeRunner) -> None:
    repo_dir = tmp_path / "existing"
    repo_dir.mkdir()
    git = Git("https://example.com/repo.git", repo_dir, runner=runner)

    with pytest.raises(FileExistsError, match="already exists"):
        git.clone(with_submodules=False)

    assert runner.calls == []


# --- update tests ---


def test_update_fetches_then_merges(tmp_path: Path, runner: FakeRunner) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    git = Git("https://example.com/repo.git", repo_dir, runner=runner)

    git.update()

    assert runner.calls == [
        ["git", "-C", str(repo_dir), "fetch", "--all", "--prune"],
        ["git", "-C", str(repo_dir), "merge", "--ff-only"],
    ]


# --- switch_and_update tests ---


def test_switch_and_update_for_branch(tmp_path: Path, runner: FakeRunner) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    git = Git("https://example.com/repo.git", repo_dir, runner=runner)

    git.switch_and_update("feature-branch", is_tag=False)

    assert runner.calls == [
        ["git", "-C", str(repo_dir), "fetch", "--all", "--prune"],
        ["git", "-C", str(repo_dir), "switch", "feature-branch"],
        ["git", "-C", str(repo_dir), "merge", "--ff-only"],
    ]


def test_switch_and_update_detaches_for_tag(tmp_path: Path, runner: FakeRunner) -> None:
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    git = Git("https://example.com/repo.git", repo_dir, runner=runner)

    git.switch_and_update("v1.2.3", is_tag=True)

    assert runner.calls == [
        ["git", "-C", str(repo_dir), "fetch", "--all", "--prune"],
        ["git", "-C", str(repo_dir), "switch", "--detach", "v1.2.3"],
        ["git", "-C", str(repo_dir), "merge", "--ff-only"],
    ]


# --- default runner tests ---


def test_default_runner_uses_subprocess() -> None:
    """Verify that Git uses subprocess.run when no runner is injected."""
    git = Git("https://example.com/repo.git", Path("/tmp/repo"))
    # Check that _runner is a partial wrapping subprocess.run
    assert git._runner.func == subprocess.run
