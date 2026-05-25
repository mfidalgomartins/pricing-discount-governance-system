from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from src.ingestion.load_raw import RAW_TABLE_DATE_COLUMNS, load_raw_tables, save_raw_tables


def _minimal_raw_tables() -> dict[str, pd.DataFrame]:
    return {
        "customers": pd.DataFrame({"customer_id": ["C001"], "signup_date": ["2024-01-01"]}),
        "products": pd.DataFrame({"product_id": ["P001"]}),
        "orders": pd.DataFrame({"order_id": ["O001"], "order_date": ["2024-02-01"]}),
        "order_items": pd.DataFrame({"order_item_id": ["OI001"]}),
        "sales_reps": pd.DataFrame({"sales_rep_id": ["R001"]}),
    }


def test_load_raw_tables_round_trip(tmp_path: Path) -> None:
    save_raw_tables(_minimal_raw_tables(), tmp_path)
    loaded = load_raw_tables(tmp_path)
    assert set(loaded.keys()) == set(RAW_TABLE_DATE_COLUMNS.keys())
    assert pd.api.types.is_datetime64_any_dtype(loaded["customers"]["signup_date"])
    assert pd.api.types.is_datetime64_any_dtype(loaded["orders"]["order_date"])


def test_load_raw_tables_raises_on_missing(tmp_path: Path) -> None:
    save_raw_tables(_minimal_raw_tables(), tmp_path)
    (tmp_path / "products.csv").unlink()

    with pytest.raises(FileNotFoundError) as excinfo:
        load_raw_tables(tmp_path)

    assert "products.csv" in str(excinfo.value)


def test_load_raw_tables_lists_all_missing(tmp_path: Path) -> None:
    # No files written at all
    with pytest.raises(FileNotFoundError) as excinfo:
        load_raw_tables(tmp_path)

    message = str(excinfo.value)
    for table in RAW_TABLE_DATE_COLUMNS:
        assert f"{table}.csv" in message
