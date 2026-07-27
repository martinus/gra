"""CLI tests for the gra commands."""

import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

from conftest import GRA, load_gra


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


# Committing must not depend on the machine having a global git identity:
# tests commit inside gra's own clones, which carry no user config.
GIT_IDENTITY = {
    "GIT_AUTHOR_NAME": "gra test",
    "GIT_AUTHOR_EMAIL": "gra@example.invalid",
    "GIT_COMMITTER_NAME": "gra test",
    "GIT_COMMITTER_EMAIL": "gra@example.invalid",
}


def git(args: list[str], cwd: Path | None = None) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        text=True,
        env={**os.environ, **GIT_IDENTITY},
    )


def git_output(args: list[str], cwd: Path | None = None) -> str:
    return subprocess.check_output(["git", *args], cwd=cwd, encoding="utf-8").strip()


def git_fails(args: list[str], cwd: Path | None = None) -> bool:
    result = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True)
    return result.returncode != 0


def make_repo(tmp_path: Path, name: str, branch: str = "main") -> Path:
    repo = tmp_path / name
    git(["init", "--initial-branch", branch, str(repo)])
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
    for word in load_gra().WORDS:
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


def test_worktree_names_match_across_gra_roots(tmp_path: Path) -> None:
    """Two machines cloning one repository land on the same worktree name."""
    source = make_repo(tmp_path, "project")
    laptop = tmp_path / "laptop"
    desktop = tmp_path / "desktop"
    laptop.mkdir()
    desktop.mkdir()

    on_laptop = clone_repo(laptop, source, work=True)
    on_desktop = clone_repo(desktop, source, work=True)

    assert worktree_dirs(on_laptop)[0].name == worktree_dirs(on_desktop)[0].name


def test_further_worktrees_take_the_next_candidates(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")

    container = clone_repo(home, source, work=True)
    first = worktree_dirs(container)[0]
    second = work_worktree(home, container)

    # A local path has no owner, so the repository name is the identity.
    preferred = load_gra().name_candidates("project")
    assert [first.name, second.name] == preferred[:2]


def test_work_creates_named_worktree_for_branch(tmp_path: Path) -> None:
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


def test_work_outside_repository_needs_a_repository_name(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()

    result = run_cli(["work"], home, cwd=tmp_path)

    assert result.returncode == 1
    assert "needs a repository when run outside one" in result.stderr


def test_work_takes_a_repository_from_anywhere(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    add_feature_branch(source, "feature/search")
    container = clone_repo(home, source)

    result = run_cli(["work", "project", "feature/search"], home, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    worktree = worktree_dirs(container)[0]
    assert git_output(["branch", "--show-current"], cwd=worktree) == "feature/search"


def test_work_with_only_a_repository_starts_detached(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source)

    result = run_cli(["work", "project"], home, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    worktree = worktree_dirs(container)[0]
    assert git_output(["branch", "--show-current"], cwd=worktree) == ""


def test_work_inside_a_repository_reads_one_argument_as_a_branch(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    add_feature_branch(source, "feature")
    container = clone_repo(home, source)
    # A repository named 'feature' exists too, so the argument is ambiguous
    # on its face: inside a repository the branch has to win.
    clone_repo(home, make_repo(tmp_path, "feature"))

    result = run_cli(["work", "feature"], home, cwd=container)

    assert result.returncode == 0, result.stderr
    worktree = worktree_dirs(container)[0]
    assert git_output(["branch", "--show-current"], cwd=worktree) == "feature"


def test_work_reports_an_unknown_repository(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    make_repo(tmp_path, "project")

    result = run_cli(["work", "nope"], home, cwd=tmp_path)

    assert result.returncode == 1
    assert "no repository 'nope'" in result.stderr


def test_work_points_at_the_worktree_holding_the_branch(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source, work=True)
    holder = worktree_dirs(container)[0]

    result = run_cli(["work", "main"], home, cwd=container)

    assert result.returncode == 1
    assert f"already checked out in '{holder.name}'" in result.stderr
    assert f"gra cd {holder.name}" in result.stderr
    assert worktree_dirs(container) == [holder]


def test_done_removes_a_named_worktree_from_anywhere(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source)
    worktree = work_worktree(home, container, "main")

    result = run_cli(["done", worktree.name], home, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert not worktree.exists()


def test_hooks_writes_only_the_missing_ones(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    container = clone_repo(home, make_repo(tmp_path, "project"))
    # Stand in for a repository cloned before hooks existed, and for one whose
    # hook the user already edited.
    (container / "done.sh").unlink()
    (container / "work.sh").write_text("#!/bin/sh\n# mine\n")

    result = run_cli(["hooks"], home)

    assert result.returncode == 0, result.stderr
    assert (container / "done.sh").is_file()
    assert os.access(container / "done.sh", os.X_OK)
    assert (container / "work.sh").read_text() == "#!/bin/sh\n# mine\n"
    assert "1 hook(s) written" in result.stdout


def test_ls_shows_ahead_and_behind(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source)
    worktree = work_worktree(home, container, "main")

    (worktree / "local.txt").write_text("local\n")
    git(["add", "local.txt"], cwd=worktree)
    git(["commit", "-m", "local"], cwd=worktree)
    # And one commit on the other side, fetched but not merged.
    (source / "remote.txt").write_text("remote\n")
    git(["add", "remote.txt"], cwd=source)
    git(["commit", "-m", "remote"], cwd=source)
    git(["fetch", "origin"], cwd=container / BARE_DIR)

    result = run_cli(["ls"], home)

    assert result.returncode == 0, result.stderr
    assert "SYNC" in result.stdout
    assert "↑1" in result.stdout
    assert "↓1" in result.stdout


def test_ls_marks_sync_as_not_applicable_without_an_upstream(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    container = clone_repo(home, make_repo(tmp_path, "project"), work=True)
    work_worktree(home, container)  # detached, so there is no upstream

    result = run_cli(["ls"], home)

    assert result.returncode == 0, result.stderr
    # '-' rather than blank: blank would read as "up to date".
    assert " - " in result.stdout


def test_ls_survives_a_worktree_whose_directory_is_gone(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    container = clone_repo(home, make_repo(tmp_path, "project"), work=True)
    shutil.rmtree(worktree_dirs(container)[0])

    result = run_cli(["ls"], home)

    assert result.returncode == 0, result.stderr
    assert "× missing" in result.stdout


def test_work_switch_to_the_branch_it_is_already_on(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source)
    worktree = work_worktree(home, container, "main")

    # The branch is checked out here, so the guard must exempt this worktree.
    result = run_cli(["work", "--switch", "main"], home, cwd=worktree)

    assert result.returncode == 0, result.stderr
    assert git_output(["branch", "--show-current"], cwd=worktree) == "main"


def recorder() -> str:
    """A hook that writes its environment and working directory to HOOK_OUT."""
    return (
        "#!/bin/sh\n"
        '{ echo "$GRA_REPO"; echo "$GRA_WORD"; echo "$GRA_BRANCH";'
        ' echo "$GRA_WORKTREE"; pwd; } > "$HOOK_OUT"\n'
    )


def write_hook(container: Path, name: str, body: str, *, executable: bool = True) -> None:
    hook = container / name
    hook.write_text(body)
    hook.chmod(0o755 if executable else 0o644)


def test_clone_writes_both_hooks_ready_to_run(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")

    container = clone_repo(home, source)

    for name in ("work.sh", "done.sh"):
        hook = container / name
        assert hook.is_file()
        # Executable from the start: the tmux behaviour gra used to provide
        # itself now lives here, so a fresh clone must work without setup.
        assert os.access(hook, os.X_OK)
        text = hook.read_text()
        for var in ("GRA_WORKTREE", "GRA_REPO", "GRA_WORD", "GRA_BRANCH"):
            assert var in text
        assert "tmux" in text


def test_work_runs_the_work_hook_inside_the_worktree(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source)
    hook_out = tmp_path / "hook-out"
    write_hook(container, "work.sh", recorder())

    result = run_cli(
        ["work", "main"], home, cwd=container, env_extra={"HOOK_OUT": str(hook_out)}
    )

    assert result.returncode == 0, result.stderr
    worktree = worktree_dirs(container)[0]
    assert hook_out.read_text().splitlines() == [
        "project",
        worktree.name,
        "main",
        str(worktree),
        str(worktree),
    ]


def test_work_skips_a_non_executable_hook(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source)
    hook_out = tmp_path / "hook-out"
    write_hook(container, "work.sh", recorder(), executable=False)

    result = run_cli(
        ["work", "main"], home, cwd=container, env_extra={"HOOK_OUT": str(hook_out)}
    )

    assert result.returncode == 0, result.stderr
    assert not hook_out.exists()


def test_work_no_hook_skips_the_hook(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source)
    hook_out = tmp_path / "hook-out"
    write_hook(container, "work.sh", recorder())

    result = run_cli(
        ["work", "--no-hook", "main"],
        home,
        cwd=container,
        env_extra={"HOOK_OUT": str(hook_out)},
    )

    assert result.returncode == 0, result.stderr
    assert not hook_out.exists()


def test_done_runs_the_done_hook_before_removing_the_worktree(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source)
    worktree = work_worktree(home, container, "main")
    hook_out = tmp_path / "hook-out"
    # The hook records whether the worktree is still there while it runs.
    write_hook(
        container,
        "done.sh",
        recorder() + '[ -d "$GRA_WORKTREE" ] && echo present >> "$HOOK_OUT"\n',
    )

    result = run_cli(["done"], home, cwd=worktree, env_extra={"HOOK_OUT": str(hook_out)})

    assert result.returncode == 0, result.stderr
    assert not worktree.exists()
    assert hook_out.read_text().splitlines() == [
        "project",
        worktree.name,
        "main",
        str(worktree),
        str(container),
        "present",
    ]


def test_clean_runs_the_done_hook_for_each_removed_worktree(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source)
    first = work_worktree(home, container, "main")
    second = work_worktree(home, container)
    hook_out = tmp_path / "hook-out"
    write_hook(container, "done.sh", '#!/bin/sh\necho "$GRA_WORD" >> "$HOOK_OUT"\n')

    result = run_cli(
        ["clean", "--yes", "--no-fetch"], home, env_extra={"HOOK_OUT": str(hook_out)}
    )

    assert result.returncode == 0, result.stderr
    assert sorted(hook_out.read_text().split()) == sorted([first.name, second.name])


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


def complete(home: Path, words: list[str], cwd: Path) -> list[str]:
    """Return what the emitted bash completion offers for a typed command line."""
    init = run_cli(["shell", "bash"], home)
    assert init.returncode == 0, init.stderr
    typed = " ".join(f'"{word}"' for word in words)
    script = (
        f"{init.stdout}\n"
        f"COMP_WORDS=({typed})\n"
        f"COMP_CWORD={len(words) - 1}\n"
        '_gra\nprintf "%s\\n" "${COMPREPLY[@]}"\n'
    )
    result = subprocess.run(
        ["bash", "-c", script],
        capture_output=True,
        text=True,
        cwd=cwd,
        env=cli_env(home),
    )
    assert result.returncode == 0, result.stderr
    return result.stdout.split()


def test_completion_is_registered_for_gra(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    init = run_cli(["shell", "bash"], home)

    result = subprocess.run(
        ["bash", "-c", f"{init.stdout}\ncomplete -p gra"],
        capture_output=True,
        text=True,
        env=cli_env(home),
    )

    # Without this the function exists but Tab never reaches it.
    assert result.returncode == 0, result.stderr
    assert "-F _gra gra" in result.stdout


def test_completion_offers_the_subcommands(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()

    assert "work" in complete(home, ["gra", ""], tmp_path)
    assert complete(home, ["gra", "cl"], tmp_path) == ["clone", "clean"]


def test_completion_offers_every_subcommand(tmp_path: Path) -> None:
    """The completion's command list is a copy of argparse's; keep them equal."""
    home = tmp_path / "home"
    home.mkdir()
    usage = run_cli(["--help"], home).stdout
    documented = set(re.search(r"\{([a-z,]+)\}", usage).group(1).split(","))

    offered = set(complete(home, ["gra", ""], tmp_path))

    assert offered == documented


def test_completion_offers_a_stray_directory_as_nothing(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    container = clone_repo(home, make_repo(tmp_path, "project"))
    worktree = work_worktree(home, container, "main")
    # Not a gra repository, so 'gra cd' could not go there anyway.
    (home / "gra" / "notes" / "2026").mkdir(parents=True)

    assert complete(home, ["gra", "cd", ""], tmp_path) == [worktree.name]


def test_completion_offers_worktree_names(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    container = clone_repo(home, make_repo(tmp_path, "project"))
    worktree = work_worktree(home, container, "main")

    assert complete(home, ["gra", "cd", ""], tmp_path) == [worktree.name]
    # A lone worktree name completes on its own rather than sharing a menu
    # with --force, which would break the common prefix bash inserts.
    assert complete(home, ["gra", "done", ""], tmp_path) == [worktree.name]
    assert complete(home, ["gra", "done", "-"], tmp_path) == ["--force"]


def test_completion_offers_repositories_outside_one(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    clone_repo(home, make_repo(tmp_path, "project"))
    clone_repo(home, make_repo(tmp_path, "other"))

    words = complete(home, ["gra", "work", ""], tmp_path)

    assert "project" in words and "other" in words


def test_completion_offers_branches_inside_a_repository(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    add_feature_branch(source, "feature/search")
    container = clone_repo(home, source)

    words = complete(home, ["gra", "work", ""], container)

    assert "main" in words
    assert "feature/search" in words
    # Inside a repository one argument is a branch, so repositories are not offered.
    assert "project" not in words


def test_completion_offers_branches_of_a_named_repository(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    add_feature_branch(source, "feature/search")
    clone_repo(home, source)

    words = complete(home, ["gra", "work", "project", "feature"], tmp_path)

    assert words == ["feature/search"]


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


def run_install(
    home: Path, env_extra: dict[str, str] | None = None
) -> subprocess.CompletedProcess[str]:
    """Install without the version check, so no test ever reaches the network."""
    return run_cli(["install", "--no-check"], home, env_extra=env_extra)


def test_install_writes_an_executable_copy(tmp_path: Path) -> None:
    home = install_home(tmp_path)

    result = run_install(home)

    assert result.returncode == 0, result.stderr
    installed = home / ".local" / "bin" / "gra"
    assert installed.read_bytes() == GRA.read_bytes()
    assert os.access(installed, os.X_OK)


def test_install_adds_shell_integration(tmp_path: Path) -> None:
    home = install_home(tmp_path)

    result = run_install(home)

    assert result.returncode == 0, result.stderr
    bashrc = (home / ".bashrc").read_text()
    assert bashrc.startswith("# existing\n")
    assert 'eval "$(gra shell bash)"' in bashrc
    assert 'export PATH="$HOME/.local/bin:$PATH"' in bashrc


def test_install_is_idempotent(tmp_path: Path) -> None:
    home = install_home(tmp_path)

    run_install(home)
    result = run_install(home)

    assert result.returncode == 0, result.stderr
    assert (home / ".bashrc").read_text().count('eval "$(gra shell bash)"') == 1


def test_install_replaces_a_symlink(tmp_path: Path) -> None:
    home = install_home(tmp_path)
    other = tmp_path / "checkout-gra"
    other.write_text("#!/bin/sh\necho old\n")
    installed = home / ".local" / "bin" / "gra"
    installed.parent.mkdir(parents=True)
    installed.symlink_to(other)

    result = run_install(home)

    assert result.returncode == 0, result.stderr
    assert not installed.is_symlink()
    assert installed.read_bytes() == GRA.read_bytes()
    assert other.read_text() == "#!/bin/sh\necho old\n"


def test_install_skips_the_path_export_when_already_on_path(tmp_path: Path) -> None:
    home = install_home(tmp_path)
    path = os.pathsep.join([str(home / ".local" / "bin"), os.environ.get("PATH", "")])

    result = run_install(home, env_extra={"PATH": path})

    assert result.returncode == 0, result.stderr
    bashrc = (home / ".bashrc").read_text()
    assert "export PATH" not in bashrc
    assert 'eval "$(gra shell bash)"' in bashrc


def test_install_without_bashrc_only_prints_instructions(tmp_path: Path) -> None:
    home = install_home(tmp_path, bashrc=None)

    result = run_install(home)

    assert result.returncode == 0, result.stderr
    assert not (home / ".bashrc").exists()
    assert 'eval "$(gra shell bash)"' in result.stdout


def test_unknown_command_is_rejected(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()

    result = run_cli(["unknown"], home)

    assert result.returncode != 0
    assert "invalid choice: 'unknown'" in result.stderr
