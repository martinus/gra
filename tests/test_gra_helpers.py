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


def test_url_helpers_support_common_git_url_shapes() -> None:
    assert gra.repo_name_from_url("https://github.com/martinus/gra.git") == "gra"
    assert gra.owner_from_url("git@github.com:martinus/gra.git") == "martinus"
    assert gra.repo_name_from_url("/tmp/repos/local-project.git") == "local-project"


@pytest.mark.parametrize("name", ["project", "project-1", "project_1", "project.1"])
def test_validate_path_name_accepts_simple_names(name: str) -> None:
    gra.validate_path_name("repository", name)


@pytest.mark.parametrize("name", ["", ".", "..", ".hidden", "has/slash", "has space"])
def test_validate_path_name_rejects_unsafe_names(name: str) -> None:
    with pytest.raises(SystemExit):
        gra.validate_path_name("repository", name)


def test_worktree_name_from_ref_sanitizes_branch_names() -> None:
    assert gra.worktree_name_from_ref("feature/search") == "feature-search"
    assert gra.worktree_name_from_ref("feature/search:query") == "feature-search-query"


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
    headers = ["REPOSITORY", "WORKTREE", "REF"]
    rows = [
        ["project", "main", "main"],
        ["project", "wt/review", "feature"],
    ]

    widths = gra.column_widths(headers, rows, include_headers=False)

    assert gra.padded_line(rows[0], widths) == "project  main       main"
    assert gra.padded_line(rows[1], widths) == "project  wt/review  feature"


def test_branch_needs_tracking_uses_local_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gra, "local_branch_exists", lambda checkout, branch: True)
    monkeypatch.setattr(gra, "remote_branch_exists", lambda checkout, branch: pytest.fail())
    monkeypatch.setattr(gra, "create_missing_branch", lambda checkout, branch: pytest.fail())

    assert gra.branch_needs_tracking(Path("repo"), "feature") is False


def test_branch_needs_tracking_uses_remote_branch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gra, "local_branch_exists", lambda checkout, branch: False)
    monkeypatch.setattr(gra, "remote_branch_exists", lambda checkout, branch: True)
    monkeypatch.setattr(gra, "create_missing_branch", lambda checkout, branch: pytest.fail())

    assert gra.branch_needs_tracking(Path("repo"), "feature") is True


def test_branch_needs_tracking_creates_missing_branch(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    created_branches: list[str] = []

    monkeypatch.setattr(gra, "local_branch_exists", lambda checkout, branch: False)
    monkeypatch.setattr(gra, "remote_branch_exists", lambda checkout, branch: False)
    monkeypatch.setattr(
        gra, "create_missing_branch", lambda checkout, branch: created_branches.append(branch)
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

    gra.fetch_repositories(
        [(Path("repo-a"), Path("repo-a/main")), (Path("repo-b"), Path("repo-b/main"))]
    )

    assert {call[1] for call in calls} == {Path("repo-a/main"), Path("repo-b/main")}
    assert all(call[0] == ["git", "fetch", "--prune", "origin"] for call in calls)
    assert all(call[4] is False for call in calls)


def test_clean_repository_entries_builds_worktree_entries_in_parallel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[Path] = []
    lock = threading.Lock()
    both_started = threading.Event()

    monkeypatch.setattr(gra, "default_checkout", lambda container: container / "main")
    monkeypatch.setattr(gra, "remote_default_branch", lambda checkout: "origin/main")
    monkeypatch.setattr(
        gra,
        "worktree_paths",
        lambda checkout: [Path("repo/main"), Path("repo/wt/feature")],
    )

    def fake_clean_worktree_entry(
        container: Path, path: Path, _default_path: Path, default_ref: str
    ) -> tuple[Path, Path, str, str, str, str]:
        with lock:
            calls.append(path)
            if len(calls) == 2:
                both_started.set()
        assert both_started.wait(1)
        return (container, path, path.name, "✓ clean", "keep", default_ref)

    monkeypatch.setattr(gra, "clean_worktree_entry", fake_clean_worktree_entry)

    entries = gra.clean_repository_entries(Path("repo"), Path("repo/main"))

    assert [entry[1] for entry in entries] == [Path("repo/main"), Path("repo/wt/feature")]