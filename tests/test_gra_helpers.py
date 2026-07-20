"""Focused tests for gra helper functions."""

import importlib.machinery
import importlib.util
import threading
from pathlib import Path
from types import ModuleType

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
GRA = REPO_ROOT / "gra"


def load_gra() -> ModuleType:
    loader = importlib.machinery.SourceFileLoader("gra_cli", str(GRA))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module


gra = load_gra()


def test_local_name_from_url_uses_owner_for_remote_urls() -> None:
    assert gra.local_name_from_url("https://github.com/martinus/gra.git") == "martinus-gra"
    assert gra.local_name_from_url("git@github.com:martinus/oans.git") == "martinus-oans"
    assert gra.local_name_from_url("ssh://git@host/team/tools.git") == "team-tools"
    assert gra.local_name_from_url("/tmp/repos/local-project.git") == "local-project"
    assert gra.local_name_from_url("file:///tmp/martinus/oans") == "martinus-oans"


def test_words_are_short_unique_and_safe() -> None:
    assert len(gra.WORDS) >= 150
    assert len(set(gra.WORDS)) == len(gra.WORDS)
    assert all(len(word) == 4 for word in gra.WORDS)
    assert all(word.isalpha() and word.islower() for word in gra.WORDS)
    commands = {"clone", "ls", "cd", "code", "shell", "tmux", "start", "done", "clean", "switch"}
    assert not commands & set(gra.WORDS)
    assert not {"main", "bare", "root"} & set(gra.WORDS)


def test_pick_worktree_name_skips_taken_names(monkeypatch: pytest.MonkeyPatch) -> None:
    taken = set(gra.WORDS) - {"wolf"}
    monkeypatch.setattr(gra, "taken_worktree_names", lambda root: taken)

    assert gra.pick_worktree_name(Path("root")) == "wolf"


def test_pick_worktree_name_fails_when_exhausted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gra, "taken_worktree_names", lambda root: set(gra.WORDS))

    with pytest.raises(SystemExit):
        gra.pick_worktree_name(Path("root"))


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
