from __future__ import annotations

import sys

import pytest

from src.ingestion.synthetic_data import SyntheticDataConfig, generate_synthetic_business_data

import scripts.run_pipeline as run_pipeline


def test_cli_rejects_non_positive_counts() -> None:
    with pytest.raises(SystemExit):
        run_pipeline.parse_args(["--customers", "-1"])

    with pytest.raises(SystemExit):
        run_pipeline.parse_args(["--orders", "0"])


def test_cli_rejects_inverted_dates() -> None:
    with pytest.raises(SystemExit):
        run_pipeline.parse_args(["--start-date", "2025-01-01", "--end-date", "2024-01-01"])


def test_pipeline_validates_raw_before_sql(monkeypatch, tmp_path) -> None:
    raw_tables = generate_synthetic_business_data(
        SyntheticDataConfig(
            seed=5,
            n_customers=20,
            n_products=28,
            n_sales_reps=4,
            n_orders=80,
            start_date="2024-01-01",
            end_date="2024-06-30",
        )
    )
    raw_tables["order_items"].loc[0, "order_id"] = "missing-order"

    monkeypatch.setattr(run_pipeline, "OUTPUTS_DIR", tmp_path)
    monkeypatch.setattr(run_pipeline, "DATA_RAW_DIR", tmp_path / "raw")
    monkeypatch.setattr(run_pipeline, "ensure_project_directories", lambda: tmp_path.mkdir(parents=True, exist_ok=True))
    monkeypatch.setattr(run_pipeline, "generate_synthetic_business_data", lambda _config: raw_tables)
    monkeypatch.setattr(run_pipeline, "save_raw_tables", lambda *_args, **_kwargs: None)

    def _sql_should_not_run(*_args, **_kwargs):
        raise AssertionError("SQL warehouse should not run before raw validation passes")

    monkeypatch.setattr(run_pipeline, "run_sql_warehouse_models", _sql_should_not_run)
    monkeypatch.setattr(sys, "argv", ["run_pipeline.py"])

    with pytest.raises(RuntimeError, match="Raw validation failed. SQL warehouse was not built"):
        run_pipeline.main()

    assert (tmp_path / "raw_validation_report.csv").exists()
