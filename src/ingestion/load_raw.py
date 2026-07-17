from __future__ import annotations

from pathlib import Path

import pandas as pd

RAW_TABLE_DATE_COLUMNS = {
    "customers": ["signup_date"],
    "orders": ["order_date"],
    "products": [],
    "order_items": [],
    "sales_reps": [],
}


def load_raw_tables(raw_dir: Path) -> dict[str, pd.DataFrame]:
    """Load every expected raw table from ``raw_dir``.

    Raises FileNotFoundError if any required table is missing, so downstream
    code can never silently operate on an incomplete dataset.
    """
    missing = [
        f"{name}.csv" for name in RAW_TABLE_DATE_COLUMNS if not (raw_dir / f"{name}.csv").exists()
    ]
    if missing:
        raise FileNotFoundError(
            f"Missing required raw CSV(s) in {raw_dir}: {', '.join(missing)}. "
            "Provide the complete source contract or run `make run` to regenerate the synthetic baseline."
        )

    return {
        name: pd.read_csv(raw_dir / f"{name}.csv", parse_dates=date_cols)
        for name, date_cols in RAW_TABLE_DATE_COLUMNS.items()
    }


def save_raw_tables(raw_tables: dict[str, pd.DataFrame], raw_dir: Path) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    for table_name, table in raw_tables.items():
        table.to_csv(raw_dir / f"{table_name}.csv", index=False)
