from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

SAFE_TABLE_NAME_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


def _as_path(path: str | Path) -> Path:
    if not isinstance(path, str | Path):
        raise TypeError(f"path must be str or Path, got {type(path).__name__}")
    return Path(path)


def _validate_table_name(name: str) -> None:
    if not isinstance(name, str) or not SAFE_TABLE_NAME_PATTERN.fullmatch(name):
        raise ValueError(
            f"Table name must contain only letters, numbers, underscores, and hyphens: {name!r}"
        )


def write_csv(df: pd.DataFrame, path: str | Path) -> None:
    if not isinstance(df, pd.DataFrame):
        raise TypeError(f"df must be a pandas DataFrame, got {type(df).__name__}")

    path = _as_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_csv(path, index=False)
    except OSError as exc:
        raise OSError(f"Failed to write CSV to {path}: {exc}") from exc


def write_text(path: str | Path, content: str, encoding: str = "utf-8") -> None:
    if not isinstance(content, str):
        raise TypeError(f"content must be str, got {type(content).__name__}")

    path = _as_path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(content, encoding=encoding)
    except OSError as exc:
        raise OSError(f"Failed to write file {path}: {exc}") from exc


def read_csv(path: str | Path, parse_dates: list[str] | None = None) -> pd.DataFrame:
    path = _as_path(path)
    try:
        return pd.read_csv(path, parse_dates=parse_dates)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"CSV file not found: {path}") from exc
    except OSError as exc:
        raise OSError(f"Failed to read CSV from {path}: {exc}") from exc


def write_table_bundle(tables: dict[str, pd.DataFrame], output_dir: str | Path) -> None:
    if not isinstance(tables, dict):
        raise TypeError(f"tables must be a dict[str, DataFrame], got {type(tables).__name__}")

    output_dir = _as_path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        _validate_table_name(name)
        write_csv(table, output_dir / f"{name}.csv")
