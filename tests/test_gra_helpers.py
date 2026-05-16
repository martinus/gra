"""Focused tests for gra helper functions."""

import importlib.machinery
import importlib.util
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