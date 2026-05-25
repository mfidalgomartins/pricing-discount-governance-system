from __future__ import annotations

from pathlib import Path

import pandas as pd


def write_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_csv(path, index=False)
    except OSError as exc:
        raise OSError(f"Failed to write CSV to {path}: {exc}") from exc


def write_text(path: Path, content: str, encoding: str = "utf-8") -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        path.write_text(content, encoding=encoding)
    except OSError as exc:
        raise OSError(f"Failed to write file {path}: {exc}") from exc


def read_csv(path: Path, parse_dates: list[str] | None = None) -> pd.DataFrame:
    return pd.read_csv(path, parse_dates=parse_dates)


def write_table_bundle(tables: dict[str, pd.DataFrame], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, table in tables.items():
        write_csv(table, output_dir / f"{name}.csv")
