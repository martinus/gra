"""Focused tests for gra helper functions."""

import subprocess
import sys
import threading
from pathlib import Path

import pytest

from conftest import GRA, load_gra


gra = load_gra()


def completed(returncode: int = 0, stderr: str = "") -> subprocess.CompletedProcess[str]:
    """What a patched subprocess.run hands back, of the type the real one does."""
    return subprocess.CompletedProcess(args=["git"], returncode=returncode, stderr=stderr)


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


def test_parse_repo_url_reads_the_host() -> None:
    assert gra.parse_repo_url("git@github.com:martinus/oans.git").host == "github.com"
    assert gra.parse_repo_url("https://github.com/martinus/oans").host == "github.com"
    assert gra.parse_repo_url("ssh://git@example.org:22/team/tools.git").host == "example.org"
    # A path has no host, so nothing will be asked about forks.
    assert gra.parse_repo_url("/tmp/repos/oans").host is None


def test_suggest_clone_name_prefers_owner() -> None:
    assert gra.suggest_clone_name("git@github.com:martinus/oans.git", "oans") == "oans-martinus"
    assert gra.suggest_clone_name("/tmp/repos/oans", "oans") == "oans-2"


def test_words_are_short_unique_and_safe() -> None:
    for words in (gra.DESCRIPTORS, gra.NOUNS):
        assert len(words) >= 60
        assert len(set(words)) == len(words)
        assert all(len(word) == 4 for word in words)
        assert all(word.isalpha() and word.islower() for word in words)
    # A word in both lists would allow doubled names like "roserose".
    assert not set(gra.DESCRIPTORS) & set(gra.NOUNS)

    # The order is per repository but the set of names is not, so this is
    # every name gra can give a worktree.
    names = set(gra.name_candidates("martinus/oans"))
    # Both words run together, and nothing gra reserves is that long - which is
    # what keeps a name from ever being read as a command or a repository path.
    assert all(len(name) == 8 for name in names)
    reserved = {"install", "clone", "fetch", "ls", "work", "switch", "done", "cd", "shell", "hooks"}
    assert not (reserved | {"main", "bare", "root", gra.BARE_DIR}) & names
    # A doubled letter where the words meet is fine (snowwolf); three in a row
    # (talllion, pureeels) is not readable, so one of the two words has to go.
    assert not [
        name
        for name in names
        if any(name[i] == name[i + 1] == name[i + 2] for i in range(len(name) - 2))
    ]


def test_pick_worktree_name_skips_taken_names(monkeypatch: pytest.MonkeyPatch) -> None:
    candidates = gra.name_candidates("martinus/oans")
    taken = set(candidates) - {candidates[7]}
    monkeypatch.setattr(gra, "taken_worktree_names", lambda root: taken)

    assert gra.pick_worktree_name(Path("root"), "martinus/oans") == candidates[7]


def test_pick_worktree_name_fails_when_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    every_name = set(gra.name_candidates("martinus/oans"))
    monkeypatch.setattr(gra, "taken_worktree_names", lambda root: every_name)

    with pytest.raises(SystemExit):
        gra.pick_worktree_name(Path("root"), "martinus/oans")


def test_pick_worktree_name_prefers_the_repositorys_own_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(gra, "taken_worktree_names", lambda root: set())
    first, second = gra.name_candidates("martinus/oans")[:2]

    assert gra.pick_worktree_name(Path("root"), "martinus/oans") == first

    # Taking a candidate shifts this repository to its next one, and nothing else.
    monkeypatch.setattr(gra, "taken_worktree_names", lambda root: {first})
    assert gra.pick_worktree_name(Path("root"), "martinus/oans") == second


def test_name_candidates_order_every_combination_per_repository() -> None:
    oans = gra.name_candidates("martinus/oans")
    other = gra.name_candidates("martinus/gra")

    # Every combination appears exactly once, so the list can neither repeat
    # nor run out: no probe budget is needed, the k-th worktree is the k-th name.
    every_name = {descriptor + noun for descriptor in gra.DESCRIPTORS for noun in gra.NOUNS}
    assert sorted(oans) == sorted(every_name)
    assert oans != other
    # The Latin-square pairing: consecutive names share neither word.
    assert all(a[:4] != b[:4] and a[4:] != b[4:] for a, b in zip(oans, oans[1:]))


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
    calls: list[tuple[list[str], Path, bool]] = []
    lock = threading.Lock()
    both_started = threading.Event()

    def fake_run(args: list[str], *, cwd: Path, check: bool, **kwargs: object) -> object:
        with lock:
            calls.append((args, cwd, check))
            if len(calls) == 2:
                both_started.set()
        # A serial implementation never gets both started, so it waits out the
        # second here and the assert turns that into a failure.
        assert both_started.wait(1)
        return completed()

    monkeypatch.setattr(gra.subprocess, "run", fake_run)

    gra.fetch_repositories([Path("root/repo-a"), Path("root/repo-b")])

    assert {call[1] for call in calls} == {Path("root/repo-a/.bare"), Path("root/repo-b/.bare")}
    assert all(call[0] == ["git", "fetch", "--prune", "--all"] for call in calls)
    assert all(call[2] is False for call in calls)


def test_fetch_repository_reports_the_last_line_of_the_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    error = "Fetching origin\nfatal: could not read from remote repository\n"
    monkeypatch.setattr(gra.subprocess, "run", lambda *a, **k: completed(128, error))

    assert gra.fetch_repository(Path("repo/.bare")) == (
        "fatal: could not read from remote repository"
    )


def script(version: str) -> bytes:
    return f'#!/usr/bin/env python3\n__version__ = "{version}"\n'.encode()


def test_version_key_orders_numerically() -> None:
    assert gra.version_key("1.10.0") > gra.version_key("1.9.0")
    assert gra.version_key("1.2.0") == gra.version_key("1.2.0")
    # An unreadable version must never look newer than a real one.
    assert gra.version_key("1.2.0-dev") < gra.version_key("0.0.1")
    assert gra.version_key(None) < gra.version_key("0.0.1")


def test_source_version_reads_without_executing() -> None:
    assert gra.source_version(script("4.5.6")) == "4.5.6"
    assert gra.source_version(b"no version here") is None


def install_sources(
    monkeypatch: pytest.MonkeyPatch, local: bytes | None, remote: bytes | None
) -> None:
    monkeypatch.setattr(gra, "local_source", lambda: local)
    monkeypatch.setattr(gra, "download_source", lambda: remote)


def test_gra_source_prefers_a_newer_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    install_sources(monkeypatch, script("1.2.0"), script("1.10.0"))

    assert gra.gra_source(check=True) == script("1.10.0")


def test_gra_source_keeps_the_local_script_unless_the_remote_is_newer(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A checkout at the released version installs itself, edits and all.
    local = script("1.2.0") + b"# local edits\n"
    install_sources(monkeypatch, local, script("1.2.0"))
    assert gra.gra_source(check=True) == local

    install_sources(monkeypatch, script("2.0.0"), script("1.2.0"))
    assert gra.gra_source(check=True) == script("2.0.0")


def test_gra_source_downloads_when_there_is_nothing_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_sources(monkeypatch, None, script("1.2.0"))

    assert gra.gra_source(check=True) == script("1.2.0")


def test_gra_source_falls_back_to_local_when_offline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_sources(monkeypatch, script("1.2.0"), None)

    # A failed check must not turn a working install into a failure.
    assert gra.gra_source(check=True) == script("1.2.0")


def test_gra_source_fails_when_offline_with_nothing_local(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    install_sources(monkeypatch, None, None)

    with pytest.raises(SystemExit):
        gra.gra_source(check=True)


def test_gra_source_skips_the_check_entirely(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gra, "local_source", lambda: script("1.2.0"))
    monkeypatch.setattr(gra, "download_source", lambda: pytest.fail("no request"))

    assert gra.gra_source(check=False) == script("1.2.0")


def test_install_reports_the_version_it_wrote(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    install_sources(monkeypatch, script("1.2.0"), script("1.10.0"))
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".bashrc").write_text("# rc\n")

    gra.install()

    installed = tmp_path / ".local" / "bin" / "gra"
    assert installed.read_bytes() == script("1.10.0")
    output = capsys.readouterr().out
    assert "upgrading gra 1.2.0 -> 1.10.0" in output
    assert "installed gra 1.10.0" in output


def test_source_version_matches_this_script() -> None:
    """Pin the regex to how gra actually writes __version__.

    If the two ever drift, both sides of the comparison read as no version,
    the tie keeps the local script, and 'gra install' silently stops
    upgrading for good.
    """
    assert gra.source_version(Path(GRA).read_bytes()) == gra.__version__
