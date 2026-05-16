"""CLI tests for the gra clone command."""

import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GRA = REPO_ROOT / "gra"


def run_cli(args: list[str], home: Path) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "GIT_CONFIG_GLOBAL": str(home / ".gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "HOME": str(home),
        }
    )
    return subprocess.run(
        [sys.executable, str(GRA), *args],
        capture_output=True,
        env=env,
        text=True,
    )


def git(args: list[str], cwd: Path | None = None) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def make_repo(tmp_path: Path, name: str, branch: str = "main") -> Path:
    repo = tmp_path / name
    git(["init", "--initial-branch", branch, str(repo)])
    git(["config", "user.email", "gra@example.invalid"], cwd=repo)
    git(["config", "user.name", "gra test"], cwd=repo)
    (repo / "README.md").write_text(f"# {name}\n")
    git(["add", "README.md"], cwd=repo)
    git(["commit", "-m", "initial"], cwd=repo)
    return repo


def test_clone_creates_flat_default_branch_checkout(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")

    result = run_cli(["clone", str(source), "--no-submodules"], home)

    assert result.returncode == 0, result.stderr
    checkout = home / "git" / "project" / "main"
    assert (checkout / ".git").is_dir()
    assert (home / "git" / "project" / "wt").is_dir()
    assert (checkout / "README.md").read_text() == "# project\n"
    assert ".claude/worktrees/" in (checkout / ".git" / "info" / "exclude").read_text()


def test_clone_supports_custom_name(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")

    result = run_cli(["clone", str(source), "--name", "project-local", "--no-submodules"], home)

    assert result.returncode == 0, result.stderr
    assert (home / "git" / "project-local" / "main" / ".git").is_dir()


def test_clone_reports_collision_with_name_suggestion(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "AFLplusplus")

    first = run_cli(["clone", str(source), "--no-submodules"], home)
    assert first.returncode == 0, first.stderr

    result = run_cli(
        ["clone", "git@github.com:martinus/AFLplusplus.git", "--no-submodules"],
        home,
    )

    assert result.returncode == 1
    assert "local repository name 'AFLplusplus' already exists" in result.stderr
    assert f"origin: {source}" in result.stderr
    assert (
        "gra clone git@github.com:martinus/AFLplusplus.git --name AFLplusplus-martinus"
        in result.stderr
    )


def test_only_clone_command_is_available(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()

    result = run_cli(["ls"], home)

    assert result.returncode != 0
    assert "invalid choice: 'ls'" in result.stderr