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
    """Run Git expecting it to fail, with the identity 'git' above also uses.

    Without it a command that commits fails on the missing identity rather
    than on what the test is about - which is exactly right on a machine with
    no global git config, such as CI.
    """
    result = subprocess.run(
        ["git", *args],
        cwd=cwd,
        capture_output=True,
        text=True,
        env={**os.environ, **GIT_IDENTITY},
    )
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
    home: Path,
    source: Path,
    name: str | None = None,
    *,
    work: bool = False,
    extra: list[str] | None = None,
    env_extra: dict[str, str] | None = None,
) -> Path:
    """Clone for tests that create their own worktrees, so --no-work by default."""
    args = ["clone", str(source)]
    if name:
        args += ["--name", name]
    if not work:
        args.append("--no-work")
    args += extra or []
    result = run_cli(args, home, env_extra=env_extra)
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
    env_extra = None
    if branch:
        args.append(branch)
    else:
        # Without a branch 'gra work' opens the branch picker; select its
        # first entry, the detached one.
        env_extra, _fzf_input, _fzf_args = write_fzf_mock(home.parent)
    before = set(worktree_dirs(container))
    result = run_cli(args, home, cwd=container, env_extra=env_extra)
    assert result.returncode == 0, result.stderr
    created = set(worktree_dirs(container)) - before
    assert len(created) == 1, result.stdout
    return created.pop()


def write_fzf_mock(
    tmp_path: Path, *, select_line: int = 1
) -> tuple[dict[str, str], Path, Path]:
    """Put a selecting-fzf on the PATH; returns (env for run_cli, input, args)."""
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
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "FZF_ARGS": str(fzf_args),
        "FZF_INPUT": str(fzf_input),
    }
    return env, fzf_input, fzf_args


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


def test_clone_checks_out_the_default_branch(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")

    container = clone_repo(home, source, work=True)

    worktrees = worktree_dirs(container)
    assert len(worktrees) == 1
    worktree = worktrees[0]
    assert len(worktree.name) == 8
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
    for name in load_gra().name_candidates("project"):
        (taken / name).mkdir()

    result = run_cli(["clone", str(source)], home)

    assert result.returncode == 1
    assert "all worktree names are taken" in result.stderr
    container = home / "gra" / "project"
    assert (container / BARE_DIR).is_dir()
    assert worktree_dirs(container) == []


def add_global_config(home: Path, text: str) -> None:
    """Append to the fake global config, so fixtures can be combined."""
    with (home / ".gitconfig").open("a") as handle:
        handle.write(text)


def make_repo_with_submodule(tmp_path: Path, home: Path) -> Path:
    """A source repository carrying a submodule, and a home that may clone it.

    Git refuses file:// submodules by default (CVE-2022-39253), so the fake
    global config the CLI runs with has to allow them.
    """
    add_global_config(home, '[protocol "file"]\n\tallow = always\n')
    child = make_repo(tmp_path, "child")
    parent = make_repo(tmp_path, "parent")
    git(
        ["-c", "protocol.file.allow=always", "submodule", "add", str(child), "lib"],
        cwd=parent,
    )
    git(["commit", "-m", "add submodule"], cwd=parent)
    return parent


def test_clone_initializes_submodules_by_default(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo_with_submodule(tmp_path, home)

    container = clone_repo(home, source, work=True)

    worktree = worktree_dirs(container)[0]
    assert (worktree / "lib" / "README.md").is_file()


def test_no_submodules_holds_for_this_and_later_worktrees(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo_with_submodule(tmp_path, home)

    container = clone_repo(home, source, work=True, extra=["--no-submodules"])
    # The flag was only given to clone, so the second worktree proves the
    # choice stuck to the repository rather than to one command line. It is
    # detached because the clone's worktree already holds main.
    later = work_worktree(home, container)

    for worktree in (worktree_dirs(container)[0], later):
        assert (worktree / ".gitmodules").is_file()
        assert not (worktree / "lib" / "README.md").exists()
    # The key the README tells people to edit by hand.
    assert (
        git_output(["config", "--get", "gra.submodules"], cwd=container / BARE_DIR)
        == "false"
    )


def github_source(tmp_path: Path, home: Path, name: str = "proj") -> str:
    """A local repository reachable at a github.com URL, via url.insteadOf.

    Lets the fork tests run offline: gra sees github.com and decides to ask
    about a parent, while git resolves the URL to a path on disk.
    """
    source = make_repo(tmp_path, name)
    url = f"git@github.com:me/{name}.git"
    add_global_config(home, f'[url "{source}"]\n\tinsteadOf = {url}\n')
    return url


def gh_mock(tmp_path: Path, parent: str = "") -> dict[str, str]:
    """A gh that reports `parent` and records that it was asked."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    gh = bin_dir / "gh"
    gh.write_text(
        "#!/bin/sh\n"
        'echo "$@" >> "$GH_CALLS"\n'
        f'echo "{parent}"\n'
    )
    gh.chmod(0o755)
    return {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "GH_CALLS": str(tmp_path / "gh-calls"),
    }


def test_clone_adds_upstream_for_a_fork(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    url = github_source(tmp_path, home)
    parent = "git@github.com:upstream/proj.git"

    result = run_cli(["clone", url], home, env_extra=gh_mock(tmp_path, parent))

    assert result.returncode == 0, result.stderr
    bare = home / "gra" / "proj" / BARE_DIR
    assert git_output(["config", "--get", "remote.upstream.url"], cwd=bare) == parent
    assert "added remote 'upstream'" in result.stdout


def test_clone_adds_no_upstream_when_it_is_not_a_fork(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    url = github_source(tmp_path, home)

    result = run_cli(["clone", url], home, env_extra=gh_mock(tmp_path))

    assert result.returncode == 0, result.stderr
    bare = home / "gra" / "proj" / BARE_DIR
    assert git_fails(["config", "--get", "remote.upstream.url"], cwd=bare)
    # gh was asked; it simply said the repository has no parent.
    assert (tmp_path / "gh-calls").is_file()


def test_clone_upstream_can_be_turned_off_for_good(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    url = github_source(tmp_path, home)
    # Without gh installed the lookup would announce itself on every GitHub
    # clone; this is the switch that stops it, rather than a flag to remember.
    add_global_config(home, "[gra]\n\tupstream = false\n")

    result = run_cli(["clone", url], home, env_extra=gh_mock(tmp_path, "x"))

    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "gh-calls").exists()


def test_clone_no_upstream_does_not_ask(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    url = github_source(tmp_path, home)

    result = run_cli(
        ["clone", url, "--no-upstream"], home, env_extra=gh_mock(tmp_path, "x")
    )

    assert result.returncode == 0, result.stderr
    assert not (tmp_path / "gh-calls").exists()


def test_clone_does_not_ask_gh_about_a_non_github_remote(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")

    result = run_cli(["clone", str(source)], home, env_extra=gh_mock(tmp_path, "x"))

    assert result.returncode == 0, result.stderr
    # A path is not a forge, so there is nothing to ask and nothing to say.
    assert not (tmp_path / "gh-calls").exists()
    assert "upstream" not in result.stdout


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

    assert len(worktree.name) == 8
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
    assert len(first.name) == len(second.name) == 8


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


def test_work_outside_a_repository_explains_every_use(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()

    result = run_cli(["work"], home, cwd=tmp_path)

    assert result.returncode == 1
    assert "gra work WORKTREE" in result.stderr
    assert "repository folder" in result.stderr
    assert "gra cd" in result.stderr


def test_work_rejects_a_second_argument(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()

    # 'gra work REPO BRANCH' is gone: work always acts where it runs.
    result = run_cli(["work", "project", "feature"], home, cwd=tmp_path)

    assert result.returncode == 2
    assert "unrecognized arguments" in result.stderr


def test_work_picks_a_branch_with_fzf_in_the_repository_folder(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    # A committer date in the future, so 'feature' outranks 'main' in the
    # recency order no matter how fast the test ran.
    git(["switch", "-c", "feature"], cwd=source)
    (source / "README.md").write_text("# feature\n")
    subprocess.run(
        ["git", "commit", "-am", "feature"],
        cwd=source,
        check=True,
        capture_output=True,
        env={
            **os.environ,
            **GIT_IDENTITY,
            "GIT_AUTHOR_DATE": "2036-01-01T12:00:00",
            "GIT_COMMITTER_DATE": "2036-01-01T12:00:00",
        },
    )
    git(["switch", "main"], cwd=source)
    container = clone_repo(home, source)
    fzf_env, fzf_input, _fzf_args = write_fzf_mock(tmp_path, select_line=2)

    result = run_cli(["work"], home, cwd=container, env_extra=fzf_env)

    assert result.returncode == 0, result.stderr
    lines = fzf_input.read_text().splitlines()
    # The detached entry leads, then branches by newest commit.
    assert "(detached)" in lines[0]
    assert lines[1].split("\t")[0] == "feature"
    assert lines[2].split("\t")[0] == "main"
    worktree = worktree_dirs(container)[0]
    assert git_output(["branch", "--show-current"], cwd=worktree) == "feature"


def test_work_picker_skips_branches_that_are_checked_out(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source, work=True)  # 'main' is taken now
    fzf_env, fzf_input, _fzf_args = write_fzf_mock(tmp_path)

    result = run_cli(["work"], home, cwd=container, env_extra=fzf_env)

    assert result.returncode == 0, result.stderr
    # Only the detached entry is offered: picking 'main' could never succeed.
    lines = fzf_input.read_text().splitlines()
    assert len(lines) == 1
    assert "(detached)" in lines[0]


def test_work_inside_a_repository_reads_one_argument_as_a_branch(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    add_feature_branch(source, "feature")
    container = clone_repo(home, source)

    result = run_cli(["work", "feature"], home, cwd=container)

    assert result.returncode == 0, result.stderr
    worktree = worktree_dirs(container)[0]
    assert git_output(["branch", "--show-current"], cwd=worktree) == "feature"


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


# ---------------------------------------------------------------------------
# tmux windows
# ---------------------------------------------------------------------------


def write_tmux_mock(
    tmp_path: Path,
    windows: str = "",
    *,
    attached: bool = True,
    sessions: str = "",
    session: str = "",
) -> tuple[dict[str, str], Path]:
    """Put a recording tmux on the PATH; returns (env for gra, log file).

    It answers what gra asks - the window list, the sessions, and which
    session a window or pane is in - and logs every call instead of touching a
    real tmux. Without attached it stands for a plain terminal, where gra
    attaches rather than switching, and still closes the windows it finds.
    An empty sessions means no tmux server is running at all.
    """
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir(exist_ok=True)
    tmux = bin_dir / "tmux"
    tmux.write_text(
        "#!/bin/sh\n"
        'printf \'%s\\n\' "$*" >> "$TMUX_LOG"\n'
        'case "$1" in\n'
        '    list-windows) printf \'%s\\n\' "$TMUX_WINDOWS" ;;\n'
        # No server running is a failure, the way the real tmux reports it.
        '    list-sessions) [ -n "$TMUX_SESSIONS" ] || exit 1\n'
        '                   printf \'%s\\n\' "$TMUX_SESSIONS" ;;\n'
        '    display-message) case "$*" in\n'
        '                         *session_name*) printf \'%s\\n\' "$TMUX_SESSION" ;;\n'
        '                         *) printf \'%s\\n\' "$TMUX_HERE" ;;\n'
        '                     esac ;;\n'
        '    new-window) printf \'%s\\n\' "$TMUX_SESSION" ;;\n'
        "esac\n"
    )
    tmux.chmod(0o755)
    log = tmp_path / "tmux-log"
    log.write_text("")
    env = {
        "PATH": f"{bin_dir}:{os.environ['PATH']}",
        "TMUX_LOG": str(log),
        "TMUX_WINDOWS": windows,
        "TMUX_SESSIONS": sessions,
        "TMUX_SESSION": session,
    }
    if attached:
        env["TMUX"] = "/tmp/tmux-test,1,0"
    return env, log


def tmux_calls(log: Path) -> list[str]:
    return log.read_text().splitlines()


def test_clone_opens_a_tmux_window_for_the_new_worktree(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    env, log = write_tmux_mock(tmp_path)

    container = clone_repo(home, source, work=True, env_extra=env)

    worktree = worktree_dirs(container)[0]
    calls = tmux_calls(log)
    assert f"new-window -n project/{worktree.name} -c {worktree}" in calls


def test_clone_no_tmux_creates_the_worktree_without_a_window(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    env, log = write_tmux_mock(tmp_path)

    container = clone_repo(home, source, work=True, extra=["--no-tmux"], env_extra=env)

    assert len(worktree_dirs(container)) == 1
    assert tmux_calls(log) == []


def test_work_opens_no_window_outside_tmux(tmp_path: Path) -> None:
    """Outside tmux there is no session a new window would belong to."""
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    env, log = write_tmux_mock(tmp_path, attached=False)
    container = clone_repo(home, source, env_extra=env)

    result = run_cli(["work", "main"], home, cwd=container, env_extra=env)

    assert result.returncode == 0, result.stderr
    assert tmux_calls(log) == []


def test_work_survives_tmux_not_being_installed(tmp_path: Path) -> None:
    """A missing tmux must not cost you the git work that came with it."""
    home = tmp_path / "home"
    home.mkdir()
    container = clone_repo(home, make_repo(tmp_path, "project"))
    # A PATH with git on it and no tmux, while TMUX says we are in a session.
    only_git = tmp_path / "only-git"
    only_git.mkdir()
    (only_git / "git").symlink_to(shutil.which("git"))
    env = {"PATH": str(only_git), "TMUX": "/tmp/tmux-test,1,0"}

    result = run_cli(["work", "main"], home, cwd=container, env_extra=env)

    assert result.returncode == 0, result.stderr
    assert len(worktree_dirs(container)) == 1


def test_work_with_a_worktree_name_opens_its_window_from_anywhere(
    tmp_path: Path,
) -> None:
    """A name identifies one worktree on the machine, so no repository needed."""
    home = tmp_path / "home"
    home.mkdir()
    container = clone_repo(home, make_repo(tmp_path, "project"))
    worktree = work_worktree(home, container, "main")
    env, log = write_tmux_mock(tmp_path)

    result = run_cli(["work", worktree.name], home, cwd=tmp_path, env_extra=env)

    assert result.returncode == 0, result.stderr
    assert f"new-window -n project/{worktree.name} -c {worktree}" in tmux_calls(log)
    # Naming a worktree sets it up; it never creates another one.
    assert worktree_dirs(container) == [worktree]


def test_work_with_a_worktree_name_switches_to_an_open_window(tmp_path: Path) -> None:
    """The window survives everything but 'gra done'; do not open a second."""
    home = tmp_path / "home"
    home.mkdir()
    container = clone_repo(home, make_repo(tmp_path, "project"))
    worktree = work_worktree(home, container, "main")
    env, log = write_tmux_mock(
        tmp_path, f"@1 project/{worktree.name}\n@2 something/else"
    )

    result = run_cli(["work", worktree.name], home, cwd=tmp_path, env_extra=env)

    assert result.returncode == 0, result.stderr
    calls = tmux_calls(log)
    assert "select-window -t @1" in calls
    assert not any(call.startswith("new-window") for call in calls)


def test_work_prefers_a_worktree_name_over_a_branch_of_the_same_name(
    tmp_path: Path,
) -> None:
    """The name is the disambiguation rule; a branch must not steal it."""
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source)
    worktree = work_worktree(home, container, "main")
    add_feature_branch(source, worktree.name)
    git(["fetch", "origin"], cwd=container / BARE_DIR)
    env, log = write_tmux_mock(tmp_path)

    result = run_cli(["work", worktree.name], home, cwd=container, env_extra=env)

    assert result.returncode == 0, result.stderr
    assert worktree_dirs(container) == [worktree]
    assert f"new-window -n project/{worktree.name} -c {worktree}" in tmux_calls(log)


def test_work_inside_a_worktree_opens_its_window(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    container = clone_repo(home, make_repo(tmp_path, "project"))
    worktree = work_worktree(home, container, "main")
    env, log = write_tmux_mock(tmp_path)

    result = run_cli(["work"], home, cwd=worktree, env_extra=env)

    assert result.returncode == 0, result.stderr
    assert f"new-window -n project/{worktree.name} -c {worktree}" in tmux_calls(log)
    assert worktree_dirs(container) == [worktree]


def test_work_inside_a_worktree_attaches_from_a_plain_terminal(tmp_path: Path) -> None:
    """Outside tmux there is no window to switch to, so gra makes one and attaches."""
    home = tmp_path / "home"
    home.mkdir()
    container = clone_repo(home, make_repo(tmp_path, "project"))
    worktree = work_worktree(home, container, "main")
    env, log = write_tmux_mock(tmp_path, attached=False, sessions="main", session="main")

    result = run_cli(["work"], home, cwd=worktree, env_extra=env)

    assert result.returncode == 0, result.stderr
    calls = tmux_calls(log)
    # -P -F names the session the window went to, which is the one to attach to.
    assert (
        f"new-window -P -F #{{session_name}} -n project/{worktree.name} -c {worktree}"
        in calls
    )
    assert "attach-session -t main" in calls


def test_work_with_a_name_attaches_to_the_session_holding_the_window(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    container = clone_repo(home, make_repo(tmp_path, "project"))
    worktree = work_worktree(home, container, "main")
    env, log = write_tmux_mock(
        tmp_path,
        f"@1 project/{worktree.name}",
        attached=False,
        sessions="work",
        session="work",
    )

    result = run_cli(["work", worktree.name], home, cwd=tmp_path, env_extra=env)

    assert result.returncode == 0, result.stderr
    calls = tmux_calls(log)
    # Attaching lands on the session's current window, so the window it holds
    # is selected first - and no second window of that name is opened.
    assert "select-window -t @1" in calls
    assert "attach-session -t work" in calls
    assert not any(call.startswith("new-window") for call in calls)


def test_work_path_prints_only_the_new_worktree(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    add_feature_branch(source)
    container = clone_repo(home, source)
    env, log = write_tmux_mock(tmp_path)

    result = run_cli(["work", "--path", "feature"], home, cwd=container, env_extra=env)

    assert result.returncode == 0, result.stderr
    created = worktree_dirs(container)[0]
    # One line, the path, and nothing else: what 'cd "$(gra work --path x)"'
    # and a Claude Code WorktreeCreate hook both need.
    assert result.stdout == f"{created}\n"
    assert git_output(["branch", "--show-current"], cwd=created) == "feature"
    # A script has no terminal to put a window in.
    assert tmux_calls(log) == []


def test_work_path_prints_an_existing_worktree_without_attaching(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    container = clone_repo(home, make_repo(tmp_path, "project"))
    worktree = work_worktree(home, container, "main")
    env, log = write_tmux_mock(tmp_path, attached=False, sessions="main", session="main")

    result = run_cli(
        ["work", "--path", worktree.name], home, cwd=tmp_path, env_extra=env
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == f"{worktree}\n"
    # Naming a worktree normally attaches; a script must not have its
    # terminal taken over.
    assert tmux_calls(log) == []


def test_work_starts_tmux_when_no_server_is_running(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    container = clone_repo(home, make_repo(tmp_path, "project"))
    worktree = work_worktree(home, container, "main")
    env, log = write_tmux_mock(tmp_path, attached=False)

    result = run_cli(["work", worktree.name], home, cwd=tmp_path, env_extra=env)

    assert result.returncode == 0, result.stderr
    calls = tmux_calls(log)
    # One command makes the session, the window, and the attach.
    assert f"new-session -n project/{worktree.name} -c {worktree}" in calls
    assert not any(call.startswith("attach-session") for call in calls)


def test_done_closes_a_window_it_is_not_running_in(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    container = clone_repo(home, make_repo(tmp_path, "project"))
    worktree = work_worktree(home, container, "main")
    env, log = write_tmux_mock(
        tmp_path,
        f"@1 project/{worktree.name}\n@2 something/else",
        attached=False,
    )

    result = run_cli(["done", worktree.name], home, cwd=tmp_path, env_extra=env)

    assert result.returncode == 0, result.stderr
    assert not worktree.exists()
    calls = tmux_calls(log)
    assert "kill-window -t @1" in calls
    assert not any("@2" in call for call in calls)
    # Nothing to defer when gra is not standing in the window.
    assert not any(call.startswith("run-shell") for call in calls)


def test_done_defers_closing_the_window_it_is_running_in(tmp_path: Path) -> None:
    """Killing that window now would kill gra before it removes anything."""
    home = tmp_path / "home"
    home.mkdir()
    container = clone_repo(home, make_repo(tmp_path, "project"))
    worktree = work_worktree(home, container, "main")
    env, log = write_tmux_mock(tmp_path, f"@1 project/{worktree.name}")
    env.update({"TMUX_PANE": "%7", "TMUX_HERE": "@1"})

    result = run_cli(["done"], home, cwd=worktree, env_extra=env)

    assert result.returncode == 0, result.stderr
    assert not worktree.exists()
    calls = tmux_calls(log)
    assert not any(call.startswith("kill-window") for call in calls)
    deferred = next(call for call in calls if call.startswith("run-shell -b"))
    # What was handed over waits for gra to exit, then closes the window only
    # if the worktree really went away - a removal that failed keeps it.
    assert "kill -0 " in deferred
    assert str(worktree) in deferred
    assert "kill-window -t @1" in deferred


def test_done_without_a_window_removes_the_worktree_anyway(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    container = clone_repo(home, make_repo(tmp_path, "project"))
    worktree = work_worktree(home, container, "main")
    env, log = write_tmux_mock(tmp_path, "@2 something/else", attached=False)

    result = run_cli(["done", worktree.name], home, cwd=tmp_path, env_extra=env)

    assert result.returncode == 0, result.stderr
    assert not worktree.exists()
    assert not any(call.startswith("kill-window") for call in tmux_calls(log))


# ---------------------------------------------------------------------------
# work
# ---------------------------------------------------------------------------



def test_work_inside_a_worktree_with_branch_creates_a_new_worktree(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    add_feature_branch(source)
    container = clone_repo(home, source)
    worktree = work_worktree(home, container, "main")

    # A branch means a new worktree even from inside one: a second task
    # arriving must not require a 'cd ..' first.
    result = run_cli(["work", "feature"], home, cwd=worktree)

    assert result.returncode == 0, result.stderr
    created = [path for path in worktree_dirs(container) if path != worktree]
    assert len(created) == 1
    assert git_output(["branch", "--show-current"], cwd=created[0]) == "feature"
    assert git_output(["branch", "--show-current"], cwd=worktree) == "main"


def test_work_finds_a_branch_by_ticket_key(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    add_feature_branch(source, "mla/OA-2345-per-processor-properties")
    container = clone_repo(home, source)

    result = run_cli(["work", "OA-2345"], home, cwd=container)

    assert result.returncode == 0, result.stderr
    worktree = worktree_dirs(container)[0]
    assert git_output(["branch", "--show-current"], cwd=worktree) == (
        "mla/OA-2345-per-processor-properties"
    )
    assert "matches branch" in result.stdout


def test_work_matches_a_ticket_key_case_insensitively(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    add_feature_branch(source, "mla/OA-2345-thing")
    container = clone_repo(home, source)

    result = run_cli(["work", "oa-2345"], home, cwd=container)

    assert result.returncode == 0, result.stderr
    worktree = worktree_dirs(container)[0]
    assert git_output(["branch", "--show-current"], cwd=worktree) == "mla/OA-2345-thing"


def test_work_prefers_an_exact_branch_over_a_longer_one(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    add_feature_branch(source, "feature")
    add_feature_branch(source, "feature-extended")
    container = clone_repo(home, source)

    result = run_cli(["work", "feature"], home, cwd=container)

    assert result.returncode == 0, result.stderr
    worktree = worktree_dirs(container)[0]
    # 'feature' is inside 'feature-extended' too, but an exact name is not a
    # guess and must never be treated as one.
    assert git_output(["branch", "--show-current"], cwd=worktree) == "feature"


def test_work_lists_several_matches_instead_of_guessing(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    add_feature_branch(source, "mla/OA-2345-first")
    add_feature_branch(source, "mla/OA-2345-second")
    container = clone_repo(home, source)

    result = run_cli(["work", "OA-2345"], home, cwd=container)

    assert result.returncode == 1
    assert "matches several branches" in result.stderr
    assert "mla/OA-2345-first" in result.stderr
    assert "mla/OA-2345-second" in result.stderr
    assert worktree_dirs(container) == []


def test_yes_creates_the_branch_without_asking(tmp_path: Path) -> None:
    """A script or a hook has nobody to answer the question."""
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source)

    # No input at all: without -y this is the prompt that fails.
    result = run_cli(["-y", "work", "OA-9999"], home, cwd=container)

    assert result.returncode == 0, result.stderr
    worktree = worktree_dirs(container)[0]
    assert git_output(["branch", "--show-current"], cwd=worktree) == "OA-9999"
    # Answering yes means what it always meant, including the push.
    assert not git_fails(
        ["show-ref", "--verify", "--quiet", "refs/heads/OA-9999"], cwd=source
    )
    # The record still shows what was decided.
    assert "does not exist. Create it from" in result.stderr


def test_yes_removes_an_unfinished_worktree_after_fetching(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source)
    worktree = work_worktree(home, container, "main")
    (worktree / "README.md").write_text("# uncommitted\n")

    result = run_cli(["-y", "done"], home, cwd=worktree)

    assert result.returncode == 0, result.stderr
    assert not worktree.exists()
    # Unlike --force, the checks still ran and are on the record.
    assert "local modification" in result.stderr


def test_work_still_offers_to_create_an_unmatched_branch(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source)

    result = run_cli(["work", "OA-9999"], home, cwd=container, input_text="n\n")

    assert result.returncode == 1
    assert "does not exist. Create it from" in result.stderr
    assert worktree_dirs(container) == []


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


def test_done_asks_about_local_modifications(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source)
    worktree = work_worktree(home, container, "main")
    (worktree / "scratch.txt").write_text("wip\n")

    refused = run_cli(["done"], home, cwd=worktree, input_text="n\n")

    assert refused.returncode == 1
    assert "✘ 1 local modification" in refused.stderr
    assert "continue? [y/N]" in refused.stderr
    assert worktree.exists()

    # Yes stands in for --force: the untracked file alone would make a plain
    # 'git worktree remove' refuse.
    accepted = run_cli(["done"], home, cwd=worktree, input_text="y\n")

    assert accepted.returncode == 0, accepted.stderr
    assert not worktree.exists()


def test_done_asks_about_an_unmerged_branch_and_keeps_it(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    add_feature_branch(source)
    container = clone_repo(home, source)
    worktree = work_worktree(home, container, "feature")
    bare = container / BARE_DIR

    refused = run_cli(["done"], home, cwd=worktree, input_text="n\n")

    assert refused.returncode == 1
    assert "✔ commits pushed to branch origin/feature" in refused.stderr
    assert "✔ no local modifications" in refused.stderr
    assert "✘ not yet merged to origin/main" in refused.stderr
    assert f"kept '{worktree}'" in refused.stderr
    assert worktree.exists()

    accepted = run_cli(["done"], home, cwd=worktree, input_text="y\n")

    assert accepted.returncode == 0, accepted.stderr
    assert not worktree.exists()
    git(["show-ref", "--verify", "--quiet", "refs/heads/feature"], cwd=bare)
    assert "kept branch 'feature'" in accepted.stdout


def test_done_reports_commits_that_are_not_pushed(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    add_feature_branch(source)
    container = clone_repo(home, source)
    worktree = work_worktree(home, container, "feature")
    (worktree / "local.txt").write_text("local\n")
    git(["add", "local.txt"], cwd=worktree)
    git(["commit", "-m", "local only"], cwd=worktree)

    refused = run_cli(["done"], home, cwd=worktree, input_text="n\n")

    assert refused.returncode == 1
    assert "✘ 1 commit not pushed to branch origin/feature" in refused.stderr
    assert "branch 'feature' will be kept" in refused.stderr
    assert worktree.exists()


def test_done_fetches_before_judging_and_accepts_a_deleted_branch(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    add_feature_branch(source)
    container = clone_repo(home, source)
    worktree = work_worktree(home, container, "feature")
    bare = container / BARE_DIR

    # The pull request workflow, after the clone: the branch is merged and
    # then deleted on the remote. Both are invisible without a fetch.
    git(["merge", "--no-ff", "-m", "merge feature", "feature"], cwd=source)
    git(["branch", "-D", "feature"], cwd=source)

    result = run_cli(["done"], home, cwd=worktree, input_text="")

    assert result.returncode == 0, result.stderr
    assert "continue?" not in result.stderr
    assert not worktree.exists()
    assert git_fails(["show-ref", "--verify", "--quiet", "refs/heads/feature"], cwd=bare)


def test_done_reports_an_interrupted_git_operation(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    add_feature_branch(source)
    # Both branches rewrote README.md, so main and feature cannot be merged
    # without a hand: exactly the half-finished state to warn about.
    (source / "README.md").write_text("# moved on\n")
    git(["commit", "-am", "main moves on"], cwd=source)
    container = clone_repo(home, source)
    worktree = work_worktree(home, container, "feature")

    assert git_fails(["merge", "origin/main"], cwd=worktree)

    refused = run_cli(["done"], home, cwd=worktree, input_text="n\n")

    assert refused.returncode == 1
    assert "✘ a merge is in progress" in refused.stderr
    assert worktree.exists()


def test_done_force_removes_an_unmerged_worktree_without_asking(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    add_feature_branch(source)
    container = clone_repo(home, source)
    worktree = work_worktree(home, container, "feature")
    bare = container / BARE_DIR

    forced = run_cli(["done", "--force"], home, cwd=worktree, input_text="")

    assert forced.returncode == 0, forced.stderr
    assert "continue?" not in forced.stderr
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


def test_ls_fetch_updates_and_prunes_every_repository(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    first = make_repo(tmp_path, "one")
    second = make_repo(tmp_path, "two")
    add_feature_branch(first)
    add_feature_branch(second)
    first_bare = clone_repo(home, first) / BARE_DIR
    second_bare = clone_repo(home, second) / BARE_DIR

    for source in (first, second):
        add_feature_branch(source, "later")
        git(["branch", "-D", "feature"], cwd=source)

    result = run_cli(["ls", "--fetch"], home, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "fetched 2 repositories" in result.stdout
    for bare in (first_bare, second_bare):
        assert not git_fails(
            ["show-ref", "--verify", "--quiet", "refs/remotes/origin/later"], cwd=bare
        )
        # --prune, so a branch gone from the remote is gone here too.
        assert git_fails(
            ["show-ref", "--verify", "--quiet", "refs/remotes/origin/feature"], cwd=bare
        )


def test_ls_fetch_updates_every_remote_not_just_origin(tmp_path: Path) -> None:
    """A fork's 'upstream' is exactly the remote that goes stale."""
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    parent = make_repo(tmp_path, "parent")
    bare = clone_repo(home, source) / BARE_DIR
    git(["remote", "add", "upstream", str(parent)], cwd=bare)
    add_feature_branch(parent)

    result = run_cli(["ls", "--fetch"], home, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert not git_fails(
        ["show-ref", "--verify", "--quiet", "refs/remotes/upstream/feature"], cwd=bare
    )


def test_ls_fetch_reports_an_unreachable_repository_and_fetches_the_rest(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    broken_bare = clone_repo(home, make_repo(tmp_path, "broken")) / BARE_DIR
    working = make_repo(tmp_path, "working")
    working_bare = clone_repo(home, working) / BARE_DIR
    git(["remote", "set-url", "origin", str(tmp_path / "gone")], cwd=broken_bare)
    add_feature_branch(working)

    result = run_cli(["ls", "--fetch"], home, cwd=tmp_path)

    # One repository nobody can reach must not cost the others their fetch.
    assert result.returncode == 0, result.stderr
    assert "broken" in result.stdout
    assert "fetched 1 of 2 repositories" in result.stdout
    assert not git_fails(
        ["show-ref", "--verify", "--quiet", "refs/remotes/origin/feature"], cwd=working_bare
    )


def test_ls_fetch_without_repositories_says_so(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()

    result = run_cli(["ls", "--fetch"], home, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert "No repositories found." in result.stdout


def test_ls_fetch_refreshes_the_sync_column(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    container = clone_repo(home, source)
    work_worktree(home, container, "main")
    (source / "README.md").write_text("# moved on\n")
    git(["commit", "-am", "second"], cwd=source)

    offline = run_cli(["ls"], home, cwd=tmp_path)

    assert offline.returncode == 0, offline.stderr
    assert "↓1" not in offline.stdout

    fetched = run_cli(["ls", "--fetch"], home, cwd=tmp_path)

    assert fetched.returncode == 0, fetched.stderr
    assert "Fetching 1 repository" in fetched.stdout
    assert "↓1" in fetched.stdout


def test_each_runs_the_command_in_every_repository(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    first = clone_repo(home, make_repo(tmp_path, "one"))
    second = clone_repo(home, make_repo(tmp_path, "two"))

    result = run_cli(["each", "touch", "marker"], home, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    # The command runs in the bare checkout, so Git commands act on the
    # repository itself rather than on one worktree.
    assert (first / BARE_DIR / "marker").is_file()
    assert (second / BARE_DIR / "marker").is_file()


def test_each_passes_flags_through_to_the_command(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    clone_repo(home, make_repo(tmp_path, "project"))

    result = run_cli(
        ["each", "git", "rev-parse", "--is-bare-repository"], home, cwd=tmp_path
    )

    assert result.returncode == 0, result.stderr
    assert "true" in result.stdout


def test_each_reports_failures_and_keeps_going(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    clone_repo(home, make_repo(tmp_path, "broken"))
    working = clone_repo(home, make_repo(tmp_path, "working"))
    (working / BARE_DIR / "marker").write_text("")

    result = run_cli(["each", "test", "-e", "marker"], home, cwd=tmp_path)

    # One repository where the command fails must not cost the others their
    # run, but it must show up in the exit status and be named.
    assert result.returncode == 1
    assert "failed in: broken" in result.stderr
    assert "working" not in result.stderr


def test_each_wt_runs_in_every_worktree(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    first = clone_repo(home, make_repo(tmp_path, "one"))
    second = clone_repo(home, make_repo(tmp_path, "two"))
    first_worktree = work_worktree(home, first, "main")
    second_worktree = work_worktree(home, second, "main")

    result = run_cli(["each", "--wt", "touch", "marker"], home, cwd=tmp_path)

    assert result.returncode == 0, result.stderr
    assert (first_worktree / "marker").is_file()
    assert (second_worktree / "marker").is_file()
    # The worktrees ran, not the repositories.
    assert not (first / BARE_DIR / "marker").exists()
    assert f"one/{first_worktree.name}:" in result.stdout


def test_each_wt_names_the_failing_worktree(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    container = clone_repo(home, make_repo(tmp_path, "project"))
    good = work_worktree(home, container, "main")
    bad = work_worktree(home, container)
    (good / "marker").write_text("")

    result = run_cli(["each", "--wt", "test", "-e", "marker"], home, cwd=tmp_path)

    assert result.returncode == 1
    assert f"failed in: project/{bad.name}" in result.stderr


def test_each_wt_without_worktrees_says_so(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    clone_repo(home, make_repo(tmp_path, "project"))

    result = run_cli(["each", "--wt", "touch", "marker"], home, cwd=tmp_path)

    # Doing nothing is correct here, but doing it silently would look like
    # the command ran.
    assert result.returncode == 0, result.stderr
    assert "No worktrees found." in result.stdout


def test_each_without_a_command_fails_with_an_example(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    clone_repo(home, make_repo(tmp_path, "project"))

    result = run_cli(["each"], home, cwd=tmp_path)

    assert result.returncode == 1
    assert "needs a command" in result.stderr


def test_each_with_an_unknown_command_says_so(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    clone_repo(home, make_repo(tmp_path, "project"))

    result = run_cli(["each", "no-such-command-zzzz"], home, cwd=tmp_path)

    assert result.returncode == 1
    assert "cannot run 'no-such-command-zzzz'" in result.stderr


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


def test_cd_requires_a_name(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    container = clone_repo(home, make_repo(tmp_path, "project"))
    work_worktree(home, container, "main")

    result = run_cli(["cd"], home, cwd=tmp_path)

    # There is no picker any more: Tab completion offers the names, and a
    # bare 'gra cd' is a usage error rather than a prompt.
    assert result.returncode == 2
    assert "name" in result.stderr


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
    assert complete(home, ["gra", "w"], tmp_path) == ["work"]


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


def test_completion_offers_branches_inside_a_repository(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    add_feature_branch(source, "feature/search")
    container = clone_repo(home, source)

    words = complete(home, ["gra", "work", ""], container)
    assert "main" in words
    assert "feature/search" in words


def test_completion_offers_command_names_for_each(tmp_path: Path) -> None:
    home = tmp_path / "home"
    home.mkdir()

    assert "git" in complete(home, ["gra", "each", "g"], tmp_path)
    assert "git" in complete(home, ["gra", "each", "--wt", "g"], tmp_path)
    assert complete(home, ["gra", "each", "-"], tmp_path) == ["--wt"]
    # The arguments belong to that command, so nothing is offered for them.
    assert complete(home, ["gra", "each", "git", ""], tmp_path) == []


def test_completion_offers_worktree_names_for_work_outside_a_repository(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    container = clone_repo(home, make_repo(tmp_path, "project"))
    worktree = work_worktree(home, container, "main")

    # 'gra work WORKTREE' works from anywhere, so the names are worth offering
    # even outside a repository - unlike branches, and unlike repository
    # names, which are no longer arguments.
    assert complete(home, ["gra", "work", ""], tmp_path) == [worktree.name]
    assert complete(home, ["gra", "work", "-"], tmp_path) == ["--path"]


def test_completion_offers_worktree_names_and_branches_for_work(
    tmp_path: Path,
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    source = make_repo(tmp_path, "project")
    add_feature_branch(source, "feature/search")
    container = clone_repo(home, source)
    worktree = work_worktree(home, container, "main")

    words = complete(home, ["gra", "work", ""], container)

    assert worktree.name in words
    assert "feature/search" in words


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
