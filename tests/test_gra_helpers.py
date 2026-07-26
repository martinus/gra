"""Focused tests for gra helper functions."""

import itertools
import sys
import threading
from pathlib import Path

import pytest

from conftest import load_gra


gra = load_gra()


def test_older_python_is_rejected_with_a_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The version guard has to fire before any 'str | Path' annotation does."""
    monkeypatch.setattr(sys, "version_info", (3, 9, 25, "final", 0))

    with pytest.raises(SystemExit) as error:
        load_gra()

    assert "gra needs Python 3.10 or newer, but this is Python 3.9" in str(error.value)


def test_repo_name_from_url_uses_last_path_component() -> None:
    assert gra.repo_name_from_url("https://github.com/martinus/gra.git") == "gra"
    assert gra.repo_name_from_url("git@github.com:martinus/oans.git") == "oans"
    assert gra.repo_name_from_url("ssh://git@host/team/tools.git") == "tools"
    assert gra.repo_name_from_url("/tmp/repos/local-project.git") == "local-project"
    assert gra.repo_name_from_url("file:///tmp/martinus/oans") == "oans"


def test_suggest_clone_name_prefers_owner() -> None:
    assert gra.suggest_clone_name("git@github.com:martinus/oans.git", "oans") == "oans-martinus"
    assert gra.suggest_clone_name("/tmp/repos/oans", "oans") == "oans-2"


def test_words_are_short_unique_and_safe() -> None:
    assert len(gra.WORDS) >= 150
    assert len(set(gra.WORDS)) == len(gra.WORDS)
    assert all(len(word) == 4 for word in gra.WORDS)
    assert all(word.isalpha() and word.islower() for word in gra.WORDS)
    commands = {"clone", "ls", "cd", "code", "shell", "tmux", "work", "done", "clean"}
    assert not commands & set(gra.WORDS)
    assert not {"main", "bare", "root"} & set(gra.WORDS)


def test_pick_worktree_name_skips_taken_names(monkeypatch: pytest.MonkeyPatch) -> None:
    taken = set(gra.WORDS) - {"wolf"}
    monkeypatch.setattr(gra, "taken_worktree_names", lambda root: taken)

    assert gra.pick_worktree_name(Path("root"), "martinus/oans") == "wolf"


def test_pick_worktree_name_fails_when_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gra, "taken_worktree_names", lambda root: set(gra.WORDS))

    with pytest.raises(SystemExit):
        gra.pick_worktree_name(Path("root"), "martinus/oans")


def test_pick_worktree_name_prefers_the_repositorys_own_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gra, "taken_worktree_names", lambda root: set())
    first, second = itertools.islice(gra.name_candidates("martinus/oans"), 2)

    assert gra.pick_worktree_name(Path("root"), "martinus/oans") == first

    # Taking a candidate shifts this repository to its next one, and nothing else.
    monkeypatch.setattr(gra, "taken_worktree_names", lambda root: {first})
    assert gra.pick_worktree_name(Path("root"), "martinus/oans") == second


def test_name_candidates_are_stable_and_repository_specific() -> None:
    oans = list(itertools.islice(gra.name_candidates("martinus/oans"), 5))
    again = list(itertools.islice(gra.name_candidates("martinus/oans"), 5))
    other = list(itertools.islice(gra.name_candidates("martinus/gra"), 5))

    assert oans == again
    assert oans != other
    assert all(word in gra.WORDS for word in oans + other)


def test_worktree_identity_normalizes_the_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    urls = {
        "ssh": "git@github.com:martinus/oans.git",
        "https": "https://github.com/martinus/oans.git",
        "no-owner": "/srv/repos/oans",
        "none": None,
    }
    monkeypatch.setattr(gra, "origin_url", lambda bare: urls[bare.parent.name])

    assert gra.worktree_identity(Path("root/ssh")) == "martinus/oans"
    assert gra.worktree_identity(Path("root/https")) == "martinus/oans"
    assert gra.worktree_identity(Path("root/no-owner")) == "oans"
    # Without a remote the container name is all there is, and it is enough:
    # the same clone on another machine has the same directory name.
    assert gra.worktree_identity(Path("root/none")) == "none"


def test_worktree_paths_skips_bare_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    porcelain = (
        "worktree /gra/project/.bare\n"
        "bare\n"
        "\n"
        "worktree /gra/project/wolf\n"
        "HEAD 1111111111111111111111111111111111111111\n"
        "branch refs/heads/feature\n"
        "\n"
        "worktree /gra/project/lynx\n"
        "HEAD 2222222222222222222222222222222222222222\n"
        "detached\n"
    )
    monkeypatch.setattr(gra, "git_output", lambda args, cwd=None: porcelain)

    assert gra.worktree_paths(Path("/gra/project/.bare")) == [
        Path("/gra/project/wolf"),
        Path("/gra/project/lynx"),
    ]


@pytest.mark.parametrize("name", ["project", "project-1", "project_1", "project.1"])
def test_validate_path_name_accepts_simple_names(name: str) -> None:
    gra.validate_path_name("repository", name)


@pytest.mark.parametrize("name", ["", ".", "..", ".hidden", "has/slash", "has space"])
def test_validate_path_name_rejects_unsafe_names(name: str) -> None:
    with pytest.raises(SystemExit):
        gra.validate_path_name("repository", name)


def test_branch_name_from_input_sanitizes_branch_names() -> None:
    assert gra.branch_name_from_input("feature/search") == "feature/search"
    assert gra.branch_name_from_input("feature/search:query") == "feature/search-query"
    assert (
        gra.branch_name_from_input(
            "mla/OA-61238 OneAgent Research Linux sources for per-processor properties parity with Windows"
        )
        == "mla/OA-61238-OneAgent-Research-Linux-sources-for-per-processor-properties-parity-with-Windows"
    )


def test_branch_name_from_input_rejects_lock_components() -> None:
    with pytest.raises(SystemExit):
        gra.branch_name_from_input("feature/foo.lock/bar")


def test_picker_formatting_can_ignore_header_widths() -> None:
    headers = ["REPOSITORY", "WORKTREE", "BRANCH"]
    rows = [
        ["project", "wolf", "main"],
        ["project", "lynx", "feature"],
    ]

    widths = gra.column_widths(headers, rows, include_headers=False)

    assert gra.padded_line(rows[0], widths) == "project  wolf  main"
    assert gra.padded_line(rows[1], widths) == "project  lynx  feature"


def test_branch_needs_tracking_uses_local_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gra, "local_branch_exists", lambda bare, branch: True)
    monkeypatch.setattr(gra, "remote_branch_exists", lambda bare, branch: pytest.fail())
    monkeypatch.setattr(gra, "create_missing_branch", lambda bare, branch: pytest.fail())

    assert gra.branch_needs_tracking(Path("repo"), "feature") is False


def test_branch_needs_tracking_uses_remote_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gra, "local_branch_exists", lambda bare, branch: False)
    monkeypatch.setattr(gra, "remote_branch_exists", lambda bare, branch: True)
    monkeypatch.setattr(gra, "create_missing_branch", lambda bare, branch: pytest.fail())

    assert gra.branch_needs_tracking(Path("repo"), "feature") is True


def test_branch_needs_tracking_creates_missing_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_branches: list[str] = []

    monkeypatch.setattr(gra, "local_branch_exists", lambda bare, branch: False)
    monkeypatch.setattr(gra, "remote_branch_exists", lambda bare, branch: False)
    monkeypatch.setattr(
        gra, "create_missing_branch", lambda bare, branch: created_branches.append(branch)
    )

    assert gra.branch_needs_tracking(Path("repo"), "feature") is False
    assert created_branches == ["feature"]


def test_fetch_repositories_runs_fetches_in_parallel(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[list[str], Path, int, int, bool]] = []
    lock = threading.Lock()
    both_started = threading.Event()

    def fake_run(
        args: list[str], *, cwd: Path, stdout: int, stderr: int, check: bool
    ) -> object:
        with lock:
            calls.append((args, cwd, stdout, stderr, check))
            if len(calls) == 2:
                both_started.set()
        assert both_started.wait(1)
        return object()

    monkeypatch.setattr(gra.subprocess, "run", fake_run)

    gra.fetch_repositories([Path("repo-a/.bare"), Path("repo-b/.bare")])

    assert {call[1] for call in calls} == {Path("repo-a/.bare"), Path("repo-b/.bare")}
    assert all(call[0] == ["git", "fetch", "--prune", "origin"] for call in calls)
    assert all(call[4] is False for call in calls)


def test_clean_repository_entries_builds_worktree_entries_in_parallel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Path] = []
    lock = threading.Lock()
    both_started = threading.Event()

    monkeypatch.setattr(gra, "remote_default_branch", lambda bare: "origin/main")
    monkeypatch.setattr(
        gra,
        "worktree_paths",
        lambda bare: [Path("repo/wolf"), Path("repo/lynx")],
    )

    def fake_clean_worktree_entry(
        path: Path, default_ref: str
    ) -> tuple[Path, str, str, str, str]:
        with lock:
            calls.append(path)
            if len(calls) == 2:
                both_started.set()
        assert both_started.wait(1)
        return (path, path.name, "✓ clean", "keep", default_ref)

    monkeypatch.setattr(gra, "clean_worktree_entry", fake_clean_worktree_entry)

    entries = gra.clean_repository_entries(Path("repo"))

    assert [entry[0] for entry in entries] == [Path("repo/wolf"), Path("repo/lynx")]
