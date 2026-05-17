"""CLI tests for the gra clone command."""

import json
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GRA = REPO_ROOT / "gra"


def run_cli(
    args: list[str],
    home: Path,
    *,
    cwd: Path | None = None,
    input_text: str | None = None,
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env.update(
        {
            "GIT_CONFIG_GLOBAL": str(home / ".gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "HOME": str(home),
        }
    )
    if env_extra:
        env.update(env_extra)
    return subprocess.run(
        [sys.executable, str(GRA), *args],
        capture_output=True,
        cwd=cwd,
        env=env,
        input=input_text,
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
    assert "● dirty" in result.stdout
    assert "▶" in result.stdout

    repo_result = run_cli(["wt"], home, cwd=home / "git" / "project")
    assert repo_result.returncode == 0, repo_result.stderr
    assert "▶" not in repo_result.stdout


def test_wt_missing_branch_can_be_declined(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")

    clone_result = run_cli(["clone", str(source), "--no-submodules"], home)
    assert clone_result.returncode == 0, clone_result.stderr
    checkout = home / "git" / "project" / "main"

    result = run_cli(
        ["wt", "NOISSUE-fix-fedora-headless"], home, cwd=checkout, input_text="n\n"
    )

    assert result.returncode == 1
    assert (
        "Branch 'NOISSUE-fix-fedora-headless' does not exist. Create it from 'origin/main'?"
        in result.stderr
    )
    assert "branch 'NOISSUE-fix-fedora-headless' was not created" in result.stderr


def test_wt_missing_branch_can_be_created_from_repo_folder(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project", branch="trunk")

    clone_result = run_cli(["clone", str(source), "--no-submodules"], home)
    assert clone_result.returncode == 0, clone_result.stderr
    container = home / "git" / "project"

    result = run_cli(
        ["wt", "NOISSUE-fix-fedora-headless"],
        home,
        cwd=container,
        input_text="y\n",
    )

    assert result.returncode == 0, result.stderr
    assert (
        "Branch 'NOISSUE-fix-fedora-headless' does not exist. Create it from 'origin/trunk'?"
        in result.stderr
    )
    worktree = container / "wt" / "NOISSUE-fix-fedora-headless"
    assert (worktree / ".git").is_file()
    assert git_output(["branch", "--show-current"], cwd=worktree) == "NOISSUE-fix-fedora-headless"
    assert (worktree / "README.md").read_text() == "# project\n"


def test_wt_missing_named_branch_can_be_created_from_wt_folder(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project", branch="master")

    clone_result = run_cli(["clone", str(source), "--no-submodules"], home)
    assert clone_result.returncode == 0, clone_result.stderr
    container = home / "git" / "project"

    result = run_cli(
        ["wt", "--name", "review", "NOISSUE-fix-fedora-headless"],
        home,
        cwd=container / "wt",
        input_text="yes\n",
    )

    assert result.returncode == 0, result.stderr
    assert (
        "Branch 'NOISSUE-fix-fedora-headless' does not exist. Create it from 'origin/master'?"
        in result.stderr
    )
    review = container / "wt" / "review"
    assert (review / ".git").is_file()
    assert git_output(["branch", "--show-current"], cwd=review) == "NOISSUE-fix-fedora-headless"
    assert (review / "README.md").read_text() == "# project\n"


def test_ls_lists_all_repositories_and_worktrees(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    project = make_repo(tmp_path, "project")
    git(["switch", "-c", "feature"], cwd=project)
    (project / "README.md").write_text("# feature\n")
    git(["commit", "-am", "feature"], cwd=project)
    git(["switch", "main"], cwd=project)
    library = make_repo(tmp_path, "library")

    project_clone = run_cli(["clone", str(project), "--no-submodules"], home)
    assert project_clone.returncode == 0, project_clone.stderr
    library_clone = run_cli(["clone", str(library), "--no-submodules"], home)
    assert library_clone.returncode == 0, library_clone.stderr

    project_checkout = home / "git" / "project" / "main"
    review_result = run_cli(["wt", "--name", "review", "feature"], home, cwd=project_checkout)
    assert review_result.returncode == 0, review_result.stderr
    review = home / "git" / "project" / "wt" / "review"
    (review / "scratch.txt").write_text("local change\n")

    result = run_cli(["ls"], home, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert f"Root: {home / 'git'}" in result.stdout
    assert "Repositories: 2" in result.stdout
    assert "Worktrees: 3" in result.stdout
    assert "REPOSITORY" in result.stdout
    assert "REMOTE" in result.stdout
    assert "library" in result.stdout
    assert "project" in result.stdout
    assert str(library) in result.stdout
    assert str(project) in result.stdout
    assert "WORKTREE" in result.stdout
    assert "REF" in result.stdout
    assert "STATUS" in result.stdout
    assert "main" in result.stdout
    assert "wt/review" in result.stdout
    assert "feature" in result.stdout
    assert "✓ clean" in result.stdout
    assert "● dirty" in result.stdout


def test_cd_prints_selected_worktree_path_from_fzf(tmp_path: Path) -> None:
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
    review_result = run_cli(["wt", "--name", "review", "feature"], home, cwd=checkout)
    assert review_result.returncode == 0, review_result.stderr

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fzf = bin_dir / "fzf"
    fzf_input = tmp_path / "fzf-input"
    fzf_args = tmp_path / "fzf-args"
    fzf.write_text(
        "#!/bin/sh\n"
        "printf '%s\n' \"$@\" > \"$FZF_ARGS\"\n"
        "cat > \"$FZF_INPUT\"\n"
        "sed -n '2p' \"$FZF_INPUT\"\n"
    )
    fzf.chmod(0o755)

    result = run_cli(
        ["cd"],
        home,
        cwd=tmp_path,
        env_extra={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "FZF_ARGS": str(fzf_args),
            "FZF_INPUT": str(fzf_input),
        },
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == f"{home / 'git' / 'project' / 'wt' / 'review'}\n"
    args = fzf_args.read_text().splitlines()
    assert "--tiebreak=begin,index" in args
    assert "--no-sort" not in args
    assert "--exact" not in args
    assert "--nth=2" not in args
    assert fzf_input.read_text().splitlines() == [
        f"{home / 'git' / 'project' / 'main'}\tproject  main       main",
        f"{home / 'git' / 'project' / 'wt' / 'review'}\tproject  wt/review  feature",
    ]


def test_code_opens_selected_worktree_path_from_fzf(tmp_path: Path) -> None:
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
    review_result = run_cli(["wt", "--name", "review", "feature"], home, cwd=checkout)
    assert review_result.returncode == 0, review_result.stderr

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    fzf = bin_dir / "fzf"
    code = bin_dir / "code"
    fzf_input = tmp_path / "fzf-input"
    fzf_args = tmp_path / "fzf-args"
    code_args = tmp_path / "code-args"
    fzf.write_text(
        "#!/bin/sh\n"
        "printf '%s\n' \"$@\" > \"$FZF_ARGS\"\n"
        "cat > \"$FZF_INPUT\"\n"
        "sed -n '2p' \"$FZF_INPUT\"\n"
    )
    fzf.chmod(0o755)
    code.write_text("#!/bin/sh\nprintf '%s\n' \"$@\" > \"$CODE_ARGS\"\n")
    code.chmod(0o755)

    result = run_cli(
        ["code"],
        home,
        cwd=tmp_path,
        env_extra={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "FZF_ARGS": str(fzf_args),
            "FZF_INPUT": str(fzf_input),
            "CODE_ARGS": str(code_args),
        },
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == f"{code} {home / 'git' / 'project' / 'wt' / 'review'}\n"
    args = fzf_args.read_text().splitlines()
    assert "--prompt=gra code> " in args
    assert "--with-nth=2" in args
    assert code_args.read_text() == f"{home / 'git' / 'project' / 'wt' / 'review'}\n"
    assert fzf_input.read_text().splitlines() == [
        f"{home / 'git' / 'project' / 'main'}\tproject  main       main",
        f"{home / 'git' / 'project' / 'wt' / 'review'}\tproject  wt/review  feature",
    ]


def test_code_worktrees_json_prints_picker_rows(tmp_path: Path) -> None:
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
    review_result = run_cli(["wt", "--name", "review", "feature"], home, cwd=checkout)
    assert review_result.returncode == 0, review_result.stderr

    result = run_cli(["code", "--worktrees-json"], home, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == [
        [str(home / "git" / "project" / "main"), ["project", "main", "main"]],
        [
            str(home / "git" / "project" / "wt" / "review"),
            ["project", "wt/review", "feature"],
        ],
    ]


def test_code_opens_selected_remote_worktree_path_from_fzf(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    ssh = bin_dir / "ssh"
    fzf = bin_dir / "fzf"
    code = bin_dir / "code"
    ssh_args = tmp_path / "ssh-args"
    fzf_input = tmp_path / "fzf-input"
    fzf_args = tmp_path / "fzf-args"
    code_args = tmp_path / "code-args"
    ssh.write_text(
        "#!/bin/sh\n"
        "printf '%s\n' \"$@\" > \"$SSH_ARGS\"\n"
        "printf '%s\n' '[[\"/home/remote/git/project/main\",[\"project\",\"main\",\"main\"]],[\"/home/remote/git/project/wt/review\",[\"project\",\"wt/review\",\"feature\"]]]'\n"
    )
    ssh.chmod(0o755)
    fzf.write_text(
        "#!/bin/sh\n"
        "printf '%s\n' \"$@\" > \"$FZF_ARGS\"\n"
        "cat > \"$FZF_INPUT\"\n"
        "sed -n '2p' \"$FZF_INPUT\"\n"
    )
    fzf.chmod(0o755)
    code.write_text("#!/bin/sh\nprintf '%s\n' \"$@\" > \"$CODE_ARGS\"\n")
    code.chmod(0o755)

    result = run_cli(
        ["code", "martinleitnerankerl@10.102.7.17"],
        home,
        cwd=tmp_path,
        env_extra={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "SSH_ARGS": str(ssh_args),
            "FZF_ARGS": str(fzf_args),
            "FZF_INPUT": str(fzf_input),
            "CODE_ARGS": str(code_args),
        },
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == (
        f"{code} --remote ssh-remote+martinleitnerankerl@10.102.7.17 "
        "/home/remote/git/project/wt/review\n"
    )
    assert ssh_args.read_text().splitlines() == [
        "-T",
        "martinleitnerankerl@10.102.7.17",
        "gra",
        "code",
        "--worktrees-json",
    ]
    args = fzf_args.read_text().splitlines()
    assert "--prompt=gra code> " in args
    assert code_args.read_text().splitlines() == [
        "--remote",
        "ssh-remote+martinleitnerankerl@10.102.7.17",
        "/home/remote/git/project/wt/review",
    ]
    assert fzf_input.read_text().splitlines() == [
        "/home/remote/git/project/main\tproject  main       main",
        "/home/remote/git/project/wt/review\tproject  wt/review  feature",
    ]


def test_shell_bash_prints_shell_helper(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()

    result = run_cli(["shell", "bash"], home)

    assert result.returncode == 0, result.stderr
    assert "gra() {" in result.stdout
    assert 'target="$(command gra cd "$@")" || return' in result.stdout
    assert "command gra \"$@\"" in result.stdout

    syntax = subprocess.run(
        ["bash", "-n"],
        input=result.stdout,
        capture_output=True,
        text=True,
    )
    assert syntax.returncode == 0, syntax.stderr


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

    result = run_cli(["unknown"], home)

    assert result.returncode != 0
    assert "invalid choice: 'unknown'" in result.stderr