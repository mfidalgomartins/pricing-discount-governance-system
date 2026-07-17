from __future__ import annotations

from pathlib import Path

import pytest

from src.utils import paths
from src.utils.paths import (
    PROJECT_ROOT,
    ensure_project_directories,
    resolve_project_path,
)


def test_resolve_project_path_accepts_relative_inside_root() -> None:
    resolved = resolve_project_path("outputs/release")

    assert resolved.is_absolute()
    assert resolved == (PROJECT_ROOT / "outputs" / "release").resolve()
    # The resolved path stays within the project root.
    resolved.relative_to(PROJECT_ROOT)


def test_resolve_project_path_accepts_absolute_inside_root() -> None:
    target = PROJECT_ROOT / "config"

    assert resolve_project_path(target) == target.resolve()


def test_resolve_project_path_rejects_traversal_outside_root() -> None:
    with pytest.raises(ValueError, match="Path escapes project root"):
        resolve_project_path("../../etc/passwd")


def test_resolve_project_path_rejects_absolute_outside_root() -> None:
    with pytest.raises(ValueError, match="Path escapes project root"):
        resolve_project_path("/tmp")


def test_ensure_project_directories_is_idempotent(monkeypatch, tmp_path) -> None:
    # Redirect the directory constants into a throwaway root so the test does
    # not touch the real project tree, then confirm the helper creates them.
    sandbox_dirs = [tmp_path / name for name in ("data/raw", "outputs", "sql/marts")]
    monkeypatch.setattr(paths, "DATA_RAW_DIR", sandbox_dirs[0])
    monkeypatch.setattr(paths, "OUTPUTS_DIR", sandbox_dirs[1])
    monkeypatch.setattr(paths, "SQL_MARTS_MODELS_DIR", sandbox_dirs[2])

    # Running twice must not raise (exist_ok=True) and must leave the dirs present.
    ensure_project_directories()
    ensure_project_directories()

    for directory in sandbox_dirs:
        assert Path(directory).is_dir()
