"""CLI tests for the gra commands."""

import importlib.machinery
import importlib.util
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
GRA = REPO_ROOT / "gra"


def gra_words() -> tuple[str, ...]:
    """The worktree name pool, loaded from the script."""
    loader = importlib.machinery.SourceFileLoader("gra_cli", str(GRA))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.WORDS
BARE_DIR = ".bare"


def cli_env(home: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("TMUX", None)
    env.update(
        {
            "GIT_CONFIG_GLOBAL": str(home / ".gitconfig"),
            "GIT_CONFIG_NOSYSTEM": "1",
            "HOME": str(home),
        }
    )
    return env


def run_cli(
    args: list[str],
    home: Path,
    *,
    cwd: Path | None = None,
    input_text: str | None = None,
    env_extra: dict[str, str] | None = None,
) -> subprocess.CompletedProcess[str]:
    env = cli_env(home)
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


def git_fails(args: list[str], cwd: Path | None = None) -> bool:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    return result.returncode != 0


def make_repo(tmp_path: Path, name: str, branch: str = "main") -> Path:
    repo = tmp_path / name
    git(["init", "--initial-branch", branch, str(repo)])
    git(["config", "user.email", "gra@example.invalid"], cwd=repo)
    git(["config", "user.name", "gra test"], cwd=repo)
    (repo / "README.md").write_text(f"# {name}\n")
    git(["add", "README.md"], cwd=repo)
    git(["commit", "-m", "initial"], cwd=repo)
    return repo


def add_feature_branch(source: Path, branch: str = "feature", base: str = "main") -> None:
    git(["switch", "-c", branch], cwd=source)
    (source / "README.md").write_text("# feature\n")
    git(["commit", "-am", "feature"], cwd=source)
    git(["switch", base], cwd=source)


def clone_repo(
    home: Path, source: Path, name: str | None = None, *, work: bool = False
) -> Path:
    """Clone for tests that create their own worktrees, so --no-work by default."""
    args = ["clone", str(source)]
    if name:
        args += ["--name", name]
    if not work:
        args.append("--no-work")
    result = run_cli(args, home)
    assert result.returncode == 0, result.stderr
    return home / "gra" / (name or source.name)


def worktree_dirs(container: Path) -> list[Path]:
    return sorted(
        child for child in container.iterdir() if child.is_dir() and child.name != BARE_DIR
    )


def work_worktree(
    home: Path, container: Path, branch: str | None = None
) -> Path:
    args = ["work"]
    if branch:
        args.append(branch)
    before = set(worktree_dirs(container))
    result = run_cli(args, home, cwd=container)
    assert result.returncode == 0, result.stderr
    created = set(worktree_dirs(container)) - before
    assert len(created) == 1, result.stdout
    return created.pop()


def write_fzf_mock(tmp_path: Path, *, select_line: int = 1) -> tuple[Path, Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    fzf = bin_dir / "fzf"
    fzf_input = tmp_path / "fzf-input"
    fzf_args = tmp_path / "fzf-args"
    fzf.write_text(
        "#!/bin/sh\n"
        "printf '%s\n' \"$@\" > \"$FZF_ARGS\"\n"
        "cat > \"$FZF_INPUT\"\n"
        f"sed -n '{select_line}p' \"$FZF_INPUT\"\n"
    )
    fzf.chmod(0o755)
    return bin_dir, fzf_input, fzf_args


def write_tmux_mock(tmp_path: Path, extra_script: str = "") -> tuple[Path, Path]:
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    tmux = bin_dir / "tmux"
    tmux_args = tmp_path / "tmux-args"
    tmux.write_text(
        "#!/bin/sh\n"
        "printf '%s\n' \"$@\" >> \"$TMUX_ARGS\"\n"
        "printf '%s\n' '---' >> \"$TMUX_ARGS\"\n" + extra_script
    )
    tmux.chmod(0o755)
    return bin_dir, tmux_args


def test_clone_with_no_work_creates_only_the_bare_repository(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")

    container = clone_repo(home, source)

    bare = container / BARE_DIR
    assert bare.is_dir()
    assert (bare / "HEAD").is_file()
    assert worktree_dirs(container) == []
    # tracks origin like a normal clone: remote refs only, no local branches
    assert (
        git_output(["config", "--get", "remote.origin.fetch"], cwd=bare)
        == "+refs/heads/*:refs/remotes/origin/*"
    )
    assert git_output(["config", "--get", "core.logAllRefUpdates"], cwd=bare) == "true"
    assert git_output(["symbolic-ref", "refs/remotes/origin/HEAD"], cwd=bare) == (
        "refs/remotes/origin/main"
    )
    git(["rev-parse", "--verify", "refs/remotes/origin/main"], cwd=bare)
    assert git_output(["branch", "--list"], cwd=bare) == ""
    exclude = (bare / "info" / "exclude").read_text()
    assert ".claude/worktrees/" in exclude
    assert ".grakeep" in exclude


def test_clone_checks_out_the_default_branch(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")

    container = clone_repo(home, source, work=True)

    worktrees = worktree_dirs(container)
    assert len(worktrees) == 1
    worktree = worktrees[0]
    assert len(worktree.name) == 4
    assert (worktree / "README.md").is_file()
    assert git_output(["rev-parse", "--abbrev-ref", "HEAD"], cwd=worktree) == "main"
    assert git_output(["rev-parse", "--abbrev-ref", "main@{upstream}"], cwd=worktree) == (
        "origin/main"
    )


def test_clone_checks_out_master_when_it_is_the_default(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project", branch="master")

    container = clone_repo(home, source, work=True)

    worktree = worktree_dirs(container)[0]
    assert git_output(["rev-parse", "--abbrev-ref", "HEAD"], cwd=worktree) == "master"


def test_clone_keeps_the_clone_when_the_remote_has_no_commits(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = tmp_path / "empty"
    git(["init", "--quiet", str(source)])

    result = run_cli(["clone", str(source)], home)

    assert result.returncode == 0, result.stderr
    assert "has no default branch yet" in result.stdout
    container = home / "gra" / "empty"
    assert (container / BARE_DIR).is_dir()
    assert worktree_dirs(container) == []


def test_clone_keeps_the_clone_when_the_worktree_cannot_be_created(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    # Every worktree name is taken, so worktree creation fails after the clone.
    taken = home / "gra" / "taken"
    (taken / BARE_DIR).mkdir(parents=True)
    for word in gra_words():
        (taken / word).mkdir()

    result = run_cli(["clone", str(source)], home)

    assert result.returncode == 1
    assert "all worktree names are taken" in result.stderr
    container = home / "gra" / "project"
    assert (container / BARE_DIR).is_dir()
    assert worktree_dirs(container) == []


def test_clone_uses_repo_name_for_remote_urls(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    owner_dir = tmp_path / "martinus"
    owner_dir.mkdir()
    source = make_repo(owner_dir, "oans")

    result = run_cli(["clone", f"file://{source}"], home)

    assert result.returncode == 0, result.stderr
    assert (home / "gra" / "oans" / BARE_DIR).is_dir()


def test_clone_supports_custom_name(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")

    container = clone_repo(home, source, name="project-local")

    assert container == home / "gra" / "project-local"
    assert (container / BARE_DIR).is_dir()


def test_clone_reports_collision_with_name_suggestion(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    clone_repo(home, source)

    result = run_cli(["clone", str(source)], home)

    assert result.returncode == 1
    assert "local repository name 'project' already exists" in result.stderr
    assert f"origin: {source}" in result.stderr
    assert "--name project-2" in result.stderr


def test_work_creates_random_worktree_for_branch(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    add_feature_branch(source, "feature/search")
    container = clone_repo(home, source)

    worktree = work_worktree(home, container, "feature/search")

    assert len(worktree.name) == 4
    assert worktree.name.isalpha()
    assert (worktree / ".git").is_file()
    assert (worktree / "README.md").read_text() == "# feature\n"
    assert git_output(["branch", "--show-current"], cwd=worktree) == "feature/search"
    assert (
        git_output(["rev-parse", "--abbrev-ref", "feature/search@{upstream}"], cwd=worktree)
        == "origin/feature/search"
    )


def test_work_without_branch_is_detached_at_origin_head(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source)

    worktree = work_worktree(home, container)

    assert git_output(["branch", "--show-current"], cwd=worktree) == ""
    assert git_output(["rev-parse", "HEAD"], cwd=worktree) == git_output(
        ["rev-parse", "origin/main"], cwd=container / BARE_DIR
    )


def test_work_worktree_names_are_unique(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source)

    first = work_worktree(home, container)
    second = work_worktree(home, container)

    assert first.name != second.name
    assert len(first.name) == len(second.name) == 4


def test_work_missing_branch_can_be_created(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project", branch="trunk")
    container = clone_repo(home, source)
    branch = "NOISSUE-fix-fedora-headless"

    result = run_cli(["work", branch], home, cwd=container, input_text="y\n")

    assert result.returncode == 0, result.stderr
    assert (
        f"Branch '{branch}' does not exist. Create it from 'origin/trunk'?" in result.stderr
    )
    worktrees = worktree_dirs(container)
    assert len(worktrees) == 1
    worktree = worktrees[0]
    assert git_output(["branch", "--show-current"], cwd=worktree) == branch
    assert (
        git_output(["rev-parse", "--abbrev-ref", f"{branch}@{{upstream}}"], cwd=worktree)
        == f"origin/{branch}"
    )
    git(["show-ref", "--verify", "--quiet", f"refs/heads/{branch}"], cwd=source)


def test_work_missing_branch_can_be_declined(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source)

    result = run_cli(["work", "nope-branch"], home, cwd=container, input_text="n\n")

    assert result.returncode == 1
    assert "branch 'nope-branch' was not created" in result.stderr
    assert worktree_dirs(container) == []


def test_work_outside_repository_fails(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()

    result = run_cli(["work"], home, cwd=tmp_path)

    assert result.returncode == 1
    assert "must be run from inside a repository" in result.stderr


def test_work_opens_tmux_window_when_inside_tmux(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source)

    bin_dir, tmux_args = write_tmux_mock(tmp_path)

    result = run_cli(
        ["work", "main"],
        home,
        cwd=container,
        env_extra={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "TMUX": "/tmp/tmux-1000/default,1234,0",
            "TMUX_ARGS": str(tmux_args),
        },
    )

    assert result.returncode == 0, result.stderr
    worktree = worktree_dirs(container)[0]
    assert tmux_args.read_text().splitlines() == [
        "new-window",
        "-P",
        "-F",
        "#{window_id}",
        "-n",
        f"project/{worktree.name}",
        "-c",
        str(worktree),
        "---",
    ]
    assert f"created tmux window 'project/{worktree.name}'" in result.stdout


def write_tmux_window_mock(tmp_path: Path, window_id: str = "@5") -> Path:
    """tmux mock that returns a window id for 'new-window -P'."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    tmux = bin_dir / "tmux"
    tmux.write_text(f"#!/bin/sh\nif [ \"$1\" = new-window ]; then echo '{window_id}'; fi\n")
    tmux.chmod(0o755)
    return bin_dir


def work_inside_tmux(
    home: Path, container: Path, tmp_path: Path, hook_out: Path
) -> subprocess.CompletedProcess[str]:
    """Run 'gra work main' inside a mocked tmux, exposing HOOK_OUT to the hook."""
    bin_dir = write_tmux_window_mock(tmp_path)
    return run_cli(
        ["work", "main"],
        home,
        cwd=container,
        env_extra={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "TMUX": "/tmp/tmux-1000/default,1234,0",
            "HOOK_OUT": str(hook_out),
        },
    )


def test_clone_writes_commented_setup_sample(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source)

    sample = container / ".tmux-setup"
    assert sample.is_file()
    assert not os.access(sample, os.X_OK)  # inert until the user opts in
    text = sample.read_text()
    for var in ("GRA_WORKTREE", "GRA_WINDOW", "GRA_REPO", "GRA_WORD", "GRA_BRANCH"):
        assert var in text
    assert "chmod +x" in text


def test_work_runs_executable_setup_hook(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source)

    hook_out = tmp_path / "hook-out"
    hook = container / ".tmux-setup"
    hook.write_text(
        "#!/bin/sh\n"
        '{ echo "$GRA_REPO"; echo "$GRA_WORD"; echo "$GRA_BRANCH";'
        ' echo "$GRA_WINDOW"; echo "$GRA_WORKTREE"; pwd; } > "$HOOK_OUT"\n'
    )
    hook.chmod(0o755)

    result = work_inside_tmux(home, container, tmp_path, hook_out)

    assert result.returncode == 0, result.stderr
    worktree = worktree_dirs(container)[0]
    assert hook_out.read_text().splitlines() == [
        "project",
        worktree.name,
        "main",
        "@5",
        str(worktree),
        str(worktree),
    ]


def test_work_skips_non_executable_setup_hook(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source)

    hook_out = tmp_path / "hook-out"
    hook = container / ".tmux-setup"
    hook.write_text('#!/bin/sh\necho ran > "$HOOK_OUT"\n')  # not executable

    result = work_inside_tmux(home, container, tmp_path, hook_out)

    assert result.returncode == 0, result.stderr
    assert not hook_out.exists()


def test_work_switch_changes_branch_in_place(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    add_feature_branch(source)
    container = clone_repo(home, source)
    worktree = work_worktree(home, container, "main")

    result = run_cli(["work", "--switch", "feature"], home, cwd=worktree)

    assert result.returncode == 0, result.stderr
    assert git_output(["branch", "--show-current"], cwd=worktree) == "feature"
    assert (worktree / "README.md").read_text() == "# feature\n"
    assert worktree_dirs(container) == [worktree]


def test_work_switch_refuses_dirty_worktree(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    add_feature_branch(source)
    container = clone_repo(home, source)
    worktree = work_worktree(home, container, "main")
    (worktree / "README.md").write_text("# local edit\n")

    result = run_cli(["work", "--switch", "feature"], home, cwd=worktree)

    assert result.returncode == 1
    assert "uncommitted changes" in result.stderr
    assert git_output(["branch", "--show-current"], cwd=worktree) == "main"


def test_work_switch_requires_branch(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()

    result = run_cli(["work", "--switch"], home, cwd=tmp_path)

    assert result.returncode == 2
    assert "--switch requires BRANCH" in result.stderr


def test_done_removes_merged_worktree_and_branch(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source)
    worktree = work_worktree(home, container, "main")
    bare = container / BARE_DIR

    result = run_cli(["done"], home, cwd=worktree)

    assert result.returncode == 0, result.stderr
    assert not worktree.exists()
    assert git_fails(["show-ref", "--verify", "--quiet", "refs/heads/main"], cwd=bare)
    assert f"removed '{worktree.name}'" in result.stdout


def test_done_refuses_dirty_worktree(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source)
    worktree = work_worktree(home, container, "main")
    (worktree / "scratch.txt").write_text("wip\n")

    result = run_cli(["done"], home, cwd=worktree)

    assert result.returncode == 1
    assert "uncommitted changes" in result.stderr
    assert worktree.exists()


def test_done_refuses_unmerged_branch_but_force_keeps_it(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    add_feature_branch(source)
    container = clone_repo(home, source)
    worktree = work_worktree(home, container, "feature")
    bare = container / BARE_DIR

    refused = run_cli(["done"], home, cwd=worktree)

    assert refused.returncode == 1
    assert "commits not in origin/main" in refused.stderr
    assert worktree.exists()

    forced = run_cli(["done", "--force"], home, cwd=worktree)

    assert forced.returncode == 0, forced.stderr
    assert not worktree.exists()
    git(["show-ref", "--verify", "--quiet", "refs/heads/feature"], cwd=bare)
    assert "kept branch 'feature'" in forced.stdout


def test_done_kills_matching_tmux_window(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source)
    worktree = work_worktree(home, container, "main")

    bin_dir, tmux_args = write_tmux_mock(
        tmp_path,
        "if [ \"$1\" = list-windows ]; then printf '%s\\t@7\\n' \"$TMUX_WORD\"; fi\n",
    )

    result = run_cli(
        ["done"],
        home,
        cwd=worktree,
        env_extra={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "TMUX_ARGS": str(tmux_args),
            "TMUX_WORD": f"project/{worktree.name}",
        },
    )

    assert result.returncode == 0, result.stderr
    lines = tmux_args.read_text().splitlines()
    assert lines == [
        "list-windows",
        "-a",
        "-F",
        "#{window_name}\t#{window_id}",
        "---",
        "kill-window",
        "-t",
        "@7",
        "---",
    ]


def test_ls_lists_all_repositories_and_worktrees(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    project = make_repo(tmp_path, "project")
    add_feature_branch(project)
    library = make_repo(tmp_path, "library")

    project_container = clone_repo(home, project)
    clone_repo(home, library)
    worktree = work_worktree(home, project_container, "feature")
    (worktree / "scratch.txt").write_text("local change\n")

    result = run_cli(["ls"], home, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert f"Root: {home / 'gra'}" in result.stdout
    assert "Repositories: 2" in result.stdout
    assert "Worktrees: 1" in result.stdout
    assert "REPOSITORY" in result.stdout
    assert "WORKTREE" in result.stdout
    assert "BRANCH" in result.stdout
    assert "STATUS" in result.stdout
    assert "REMOTE" in result.stdout
    assert "library" in result.stdout
    assert "project" in result.stdout
    assert str(library) in result.stdout
    assert str(project) in result.stdout
    assert worktree.name in result.stdout
    assert "feature" in result.stdout
    assert "● dirty" in result.stdout


def test_clean_treats_squash_merged_worktree_as_removable(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    add_feature_branch(source)
    container = clone_repo(home, source)
    worktree = work_worktree(home, container, "feature")
    bare = container / BARE_DIR

    git(["merge", "--squash", "feature"], cwd=source)
    git(["commit", "-m", "squash feature"], cwd=source)

    dry_run = run_cli(["clean"], home, cwd=tmp_path)

    assert dry_run.returncode == 0, dry_run.stderr
    assert worktree.name in dry_run.stdout
    assert "remove" in dry_run.stdout
    assert "Dry run. Re-run with --yes to remove 1 worktree(s)." in dry_run.stdout

    apply_run = run_cli(["clean", "--yes"], home, cwd=tmp_path)

    assert apply_run.returncode == 0, apply_run.stderr
    assert not worktree.exists()
    assert git_fails(["show-ref", "--verify", "--quiet", "refs/heads/feature"], cwd=bare)


def test_clean_keeps_grakeep_worktree(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    add_feature_branch(source)
    container = clone_repo(home, source)
    worktree = work_worktree(home, container, "feature")
    (worktree / ".grakeep").write_text("")

    assert git_output(["status", "--porcelain", "--", ".grakeep"], cwd=worktree) == ""

    git(["merge", "--squash", "feature"], cwd=source)
    git(["commit", "-m", "squash feature"], cwd=source)

    result = run_cli(["clean"], home, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert worktree.name in result.stdout
    assert ".grakeep marker" in result.stdout
    assert "Nothing to clean." in result.stdout
    assert "Dry run. Re-run" not in result.stdout


def test_cd_with_name_prints_worktree_path(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source)
    worktree = work_worktree(home, container, "main")

    result = run_cli(["cd", worktree.name], home, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert result.stdout == f"{worktree}\n"


def test_cd_with_unknown_name_fails(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    clone_repo(home, source)

    result = run_cli(["cd", "zzzz"], home, cwd=tmp_path)

    assert result.returncode == 1
    assert "no worktree named 'zzzz'" in result.stderr


def test_cd_prints_selected_worktree_path_from_fzf(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source)
    worktree = work_worktree(home, container, "main")

    bin_dir, fzf_input, fzf_args = write_fzf_mock(tmp_path)

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
    assert result.stdout == f"{worktree}\n"
    args = fzf_args.read_text().splitlines()
    assert "--tiebreak=begin,index" in args
    assert "--with-nth=2" in args
    assert fzf_input.read_text().splitlines() == [
        f"{worktree}\tproject  {worktree.name}  main",
    ]


def test_tmux_with_name_creates_window_for_worktree(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source)
    worktree = work_worktree(home, container, "main")

    bin_dir, tmux_args = write_tmux_mock(
        tmp_path, "if [ \"$1\" = has-session ]; then exit 1; fi\n"
    )

    result = run_cli(
        ["tmux", worktree.name],
        home,
        cwd=tmp_path,
        env_extra={
            "PATH": f"{bin_dir}:{os.environ['PATH']}",
            "TMUX_ARGS": str(tmux_args),
        },
    )

    assert result.returncode == 0, result.stderr
    assert (
        f"created tmux session 'main' with window 'project/{worktree.name}'"
        in result.stdout
    )
    assert tmux_args.read_text().splitlines() == [
        "has-session",
        "-t",
        "main",
        "---",
        "new-session",
        "-d",
        "-s",
        "main",
        "-n",
        f"project/{worktree.name}",
        "-c",
        str(worktree),
        "---",
    ]


def test_shell_bash_prints_shell_helper(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()

    result = run_cli(["shell", "bash"], home)

    assert result.returncode == 0, result.stderr
    assert "gra() {" in result.stdout
    assert 'target="$(command gra cd "$@")" || return' in result.stdout
    assert "command gra \"$@\"" in result.stdout
    assert "done)" in result.stdout

    syntax = subprocess.run(
        ["bash", "-n"],
        input=result.stdout,
        capture_output=True,
        text=True,
    )
    assert syntax.returncode == 0, syntax.stderr


def test_shell_bash_done_leaves_removed_directory(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source)
    worktree = work_worktree(home, container, "main")

    init = run_cli(["shell", "bash"], home)
    assert init.returncode == 0, init.stderr

    env = cli_env(home)
    script = (
        f"gra() {{ :; }}\n{init.stdout}\n"
        f'command() {{ shift; "{sys.executable}" "{GRA}" "$@"; }}\n'
        f'cd "{worktree}"\ngra done >/dev/null 2>&1\npwd\n'
    )
    result = subprocess.run(
        ["bash", "-c", script], capture_output=True, text=True, env=env
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == str(container)
    assert not worktree.exists()


def install_home(tmp_path: Path, *, bashrc: str | None = "# existing\n") -> Path:
    home = tmp_path / "home"
    home.mkdir()
    if bashrc is not None:
        (home / ".bashrc").write_text(bashrc)
    return home


def test_install_writes_an_executable_copy(tmp_path: Path) -> None:
    home = install_home(tmp_path)

    result = run_cli(["install"], home)

    assert result.returncode == 0, result.stderr
    installed = home / ".local" / "bin" / "gra"
    assert installed.read_bytes() == GRA.read_bytes()
    assert os.access(installed, os.X_OK)


def test_install_adds_shell_integration(tmp_path: Path) -> None:
    home = install_home(tmp_path)

    result = run_cli(["install"], home)

    assert result.returncode == 0, result.stderr
    bashrc = (home / ".bashrc").read_text()
    assert bashrc.startswith("# existing\n")
    assert 'eval "$(gra shell bash)"' in bashrc
    assert 'export PATH="$HOME/.local/bin:$PATH"' in bashrc


def test_install_is_idempotent(tmp_path: Path) -> None:
    home = install_home(tmp_path)

    run_cli(["install"], home)
    result = run_cli(["install"], home)

    assert result.returncode == 0, result.stderr
    assert (home / ".bashrc").read_text().count('eval "$(gra shell bash)"') == 1


def test_install_replaces_a_symlink(tmp_path: Path) -> None:
    home = install_home(tmp_path)
    other = tmp_path / "checkout-gra"
    other.write_text("#!/bin/sh\necho old\n")
    installed = home / ".local" / "bin" / "gra"
    installed.parent.mkdir(parents=True)
    installed.symlink_to(other)

    result = run_cli(["install"], home)

    assert result.returncode == 0, result.stderr
    assert not installed.is_symlink()
    assert installed.read_bytes() == GRA.read_bytes()
    assert other.read_text() == "#!/bin/sh\necho old\n"


def test_install_skips_the_path_export_when_already_on_path(tmp_path: Path) -> None:
    home = install_home(tmp_path)
    path = os.pathsep.join([str(home / ".local" / "bin"), os.environ.get("PATH", "")])

    result = run_cli(["install"], home, env_extra={"PATH": path})

    assert result.returncode == 0, result.stderr
    bashrc = (home / ".bashrc").read_text()
    assert "export PATH" not in bashrc
    assert 'eval "$(gra shell bash)"' in bashrc


def test_install_without_bashrc_only_prints_instructions(tmp_path: Path) -> None:
    home = install_home(tmp_path, bashrc=None)

    result = run_cli(["install"], home)

    assert result.returncode == 0, result.stderr
    assert not (home / ".bashrc").exists()
    assert 'eval "$(gra shell bash)"' in result.stdout


def test_unknown_command_is_rejected(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()

    result = run_cli(["unknown"], home)

    assert result.returncode != 0
    assert "invalid choice: 'unknown'" in result.stderr
