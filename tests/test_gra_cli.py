"""CLI tests for the gra clone command."""

import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GRA = REPO_ROOT / "gra"


def run_cli(
    args: list[str], home: Path, *, cwd: Path | None = None
) -> subprocess.CompletedProcess[str]:
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
        cwd=cwd,
        env=env,
        text=True,
    )


def git(args: list[str], cwd: Path | None = None) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


def git_output(args: list[str], cwd: Path | None = None) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, encoding="utf-8").strip()


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


def test_wt_creates_branch_named_worktree(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    git(["switch", "-c", "feature/search"], cwd=source)
    (source / "README.md").write_text("# feature\n")
    git(["commit", "-am", "feature"], cwd=source)
    git(["switch", "main"], cwd=source)

    clone_result = run_cli(["clone", str(source), "--no-submodules"], home)
    assert clone_result.returncode == 0, clone_result.stderr
    checkout = home / "git" / "project" / "main"

    result = run_cli(["wt", "feature/search"], home, cwd=checkout)

    assert result.returncode == 0, result.stderr
    feature = home / "git" / "project" / "wt" / "feature-search"
    assert (feature / ".git").is_file()
    assert (feature / "README.md").read_text() == "# feature\n"
    assert git_output(["branch", "--show-current"], cwd=feature) == "feature/search"


def test_wt_creates_reusable_named_review_worktree(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    first_branch = "feature/OA-65510-implement-gcp-support-for-serialid"
    second_branch = "feature/OA-65511-review-followup"
    git(["switch", "-c", first_branch], cwd=source)
    (source / "README.md").write_text("# feature\n")
    git(["commit", "-am", "feature"], cwd=source)
    git(["switch", "-c", second_branch], cwd=source)
    (source / "README.md").write_text("# followup\n")
    git(["commit", "-am", "followup"], cwd=source)
    git(["switch", "main"], cwd=source)

    clone_result = run_cli(["clone", str(source), "--no-submodules"], home)
    assert clone_result.returncode == 0, clone_result.stderr
    container = home / "git" / "project"

    create_result = run_cli(["wt", "--name", "review", first_branch], home, cwd=container)

    assert create_result.returncode == 0, create_result.stderr
    review = home / "git" / "project" / "wt" / "review"
    assert (review / ".git").is_file()
    assert (review / "README.md").read_text() == "# feature\n"
    assert git_output(["branch", "--show-current"], cwd=review) == first_branch

    switch_result = run_cli(["wt", "--name", "review", second_branch], home, cwd=container / "wt")

    assert switch_result.returncode == 0, switch_result.stderr
    assert (review / "README.md").read_text() == "# followup\n"
    assert git_output(["branch", "--show-current"], cwd=review) == second_branch


def test_wt_lists_worktrees_for_current_repo(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    git(["switch", "-c", "feature"], cwd=source)
    (source / "README.md").write_text("# feature\n")
    git(["commit", "-am", "feature"], cwd=source)
    git(["switch", "main"], cwd=source)

    clone_result = run_cli(["clone", str(source), "--no-submodules"], home)
    assert clone_result.returncode == 0, clone_result.stderr
    checkout = home / "git" / "project" / "main"
    create_result = run_cli(["wt", "--name", "review", "feature"], home, cwd=checkout)
    assert create_result.returncode == 0, create_result.stderr
    review = home / "git" / "project" / "wt" / "review"
    (review / "scratch.txt").write_text("local change\n")

    result = run_cli(["wt"], home, cwd=review)

    assert result.returncode == 0, result.stderr
    assert "WORKTREE" in result.stdout
    assert "REF" in result.stdout
    assert "STATUS" in result.stdout
    assert "main" in result.stdout
    assert "wt/review" in result.stdout
    assert "feature" in result.stdout
    assert "dirty" in result.stdout

    repo_result = run_cli(["wt"], home, cwd=home / "git" / "project")
    assert repo_result.returncode == 0, repo_result.stderr
    assert "*  main" not in repo_result.stdout
    assert "*  wt/review" not in repo_result.stdout


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


def test_unknown_command_is_rejected(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()

    result = run_cli(["ls"], home)

    assert result.returncode != 0
    assert "invalid choice: 'ls'" in result.stderr