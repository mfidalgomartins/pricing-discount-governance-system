from __future__ import annotations

from pathlib import Path
from typing import Dict

import pandas as pd


RAW_TABLE_DATE_COLUMNS = {
    "customers": ["signup_date"],
    "orders": ["order_date"],
    "products": [],
    "order_items": [],
    "sales_reps": [],
}


def load_raw_tables(raw_dir: Path) -> Dict[str, pd.DataFrame]:
    tables: Dict[str, pd.DataFrame] = {}
    for table_name, date_cols in RAW_TABLE_DATE_COLUMNS.items():
        table_path = raw_dir / f"{table_name}.csv"
        if table_path.exists():
            tables[table_name] = pd.read_csv(table_path, parse_dates=date_cols)
    return tables


def save_raw_tables(raw_tables: Dict[str, pd.DataFrame], raw_dir: Path) -> None:
    raw_dir.mkdir(parents=True, exist_ok=True)
    for table_name, table in raw_tables.items():
        table.to_csv(raw_dir / f"{table_name}.csv", index=False)
