from __future__ import annotations

import json
import sys

import pytest

import scripts.publish_pages_dashboard as publish_dashboard
import scripts.run_pipeline as run_pipeline
from src.ingestion.synthetic_data import SyntheticDataConfig, generate_synthetic_business_data


def test_cli_rejects_non_positive_counts() -> None:
    with pytest.raises(SystemExit):
        run_pipeline.parse_args(["--customers", "-1"])

    with pytest.raises(SystemExit):
        run_pipeline.parse_args(["--orders", "0"])


def test_cli_rejects_inverted_dates() -> None:
    with pytest.raises(SystemExit):
        run_pipeline.parse_args(["--start-date", "2025-01-01", "--end-date", "2024-01-01"])


def test_cli_rejects_non_canonical_date_format() -> None:
    with pytest.raises(SystemExit):
        run_pipeline.parse_args(["--start-date", "20240101"])


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
    monkeypatch.setattr(
        run_pipeline,
        "ensure_project_directories",
        lambda: tmp_path.mkdir(parents=True, exist_ok=True),
    )
    monkeypatch.setattr(
        run_pipeline, "generate_synthetic_business_data", lambda _config: raw_tables
    )
    monkeypatch.setattr(run_pipeline, "save_raw_tables", lambda *_args, **_kwargs: None)

    def _sql_should_not_run(*_args, **_kwargs):
        raise AssertionError("SQL warehouse should not run before raw validation passes")

    monkeypatch.setattr(run_pipeline, "run_sql_warehouse_models", _sql_should_not_run)
    monkeypatch.setattr(sys, "argv", ["run_pipeline.py"])

    with pytest.raises(RuntimeError, match=r"Raw validation failed\. SQL warehouse was not built"):
        run_pipeline.main()

    assert (tmp_path / "raw_validation_report.csv").exists()


def test_dashboard_publication_requires_passing_release_gate(monkeypatch) -> None:
    publish_calls = 0

    def record_publish() -> None:
        nonlocal publish_calls
        publish_calls += 1

    monkeypatch.setattr(run_pipeline, "publish_pages_dashboard", record_publish)

    with pytest.raises(RuntimeError, match="Dashboard was not published"):
        run_pipeline.publish_validated_dashboard(False)
    assert publish_calls == 0

    run_pipeline.publish_validated_dashboard(True)
    assert publish_calls == 1


def test_run_manifest_paths_are_repository_relative() -> None:
    path = run_pipeline.PROJECT_ROOT / "outputs" / "run_manifest.json"

    assert run_pipeline._repository_path(path) == "outputs/run_manifest.json"


def test_standalone_publisher_rejects_missing_or_failed_gate(monkeypatch, tmp_path) -> None:
    gate_report = tmp_path / "release_gate_report.json"
    monkeypatch.setattr(publish_dashboard, "RELEASE_GATE_REPORT", gate_report)

    with pytest.raises(FileNotFoundError, match="Release gate report is missing"):
        publish_dashboard.publish()

    gate_report.write_text(json.dumps({"gate_passed": False}), encoding="utf-8")
    with pytest.raises(RuntimeError, match="publication is blocked"):
        publish_dashboard.publish()


def test_standalone_publisher_rejects_dashboard_changed_after_gate(monkeypatch, tmp_path) -> None:
    gate_report = tmp_path / "release_gate_report.json"
    dashboard = tmp_path / "dashboard.html"
    vendor = tmp_path / "chart.umd.min.js"
    gate_report.write_text(
        json.dumps({"gate_passed": True, "dashboard_sha256": "stale-hash"}),
        encoding="utf-8",
    )
    dashboard.write_text('<script src="vendor/chart.umd.min.js"></script>', encoding="utf-8")
    vendor.write_text("chart", encoding="utf-8")

    monkeypatch.setattr(publish_dashboard, "RELEASE_GATE_REPORT", gate_report)
    monkeypatch.setattr(publish_dashboard, "OUTPUTS_DASHBOARD", dashboard)
    monkeypatch.setattr(publish_dashboard, "OUTPUTS_VENDOR", vendor)

    with pytest.raises(RuntimeError, match="Dashboard changed after validation"):
        publish_dashboard.publish()
