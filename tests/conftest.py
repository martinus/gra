"""Shared test fixtures and helpers."""

import importlib.machinery
import importlib.util
from pathlib import Path
from types import ModuleType


REPO_ROOT = Path(__file__).resolve().parents[1]
GRA = REPO_ROOT / "gra"


def load_gra() -> ModuleType:
    """Import the extensionless gra script as a module."""
    loader = importlib.machinery.SourceFileLoader("gra_cli", str(GRA))
    spec = importlib.util.spec_from_loader(loader.name, loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module
