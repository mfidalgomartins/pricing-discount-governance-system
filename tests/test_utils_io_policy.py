from __future__ import annotations

import json

import pandas as pd
import pytest

from src.utils.io import read_csv, write_csv, write_table_bundle, write_text
from src.utils.policy import _assert_weight_sum, get_high_discount_threshold, load_policy_thresholds
from src.validation.data_quality import validate_processed_tables


def test_io_helpers_round_trip_csv_text_and_bundle(tmp_path) -> None:
    frame = pd.DataFrame({"order_date": ["2024-01-01"], "line_revenue": [100.0]})
    csv_path = tmp_path / "nested" / "table.csv"
    text_path = tmp_path / "nested" / "note.md"
    bundle_dir = tmp_path / "bundle"

    write_csv(frame, csv_path)
    write_text(text_path, "conteudo operacional")
    write_table_bundle({"orders": frame}, bundle_dir)

    loaded = read_csv(csv_path, parse_dates=["order_date"])

    assert loaded["order_date"].dt.strftime("%Y-%m-%d").iloc[0] == "2024-01-01"
    assert loaded["line_revenue"].iloc[0] == 100.0
    assert text_path.read_text(encoding="utf-8") == "conteudo operacional"
    assert (bundle_dir / "orders.csv").exists()


def test_io_helpers_raise_contextual_os_errors(tmp_path, monkeypatch) -> None:
    def raise_os_error(*_args, **_kwargs) -> None:
        raise OSError("disk unavailable")

    monkeypatch.setattr(pd.DataFrame, "to_csv", raise_os_error)

    with pytest.raises(OSError, match="Failed to write CSV"):
        write_csv(pd.DataFrame({"a": [1]}), tmp_path / "out.csv")

    blocked_parent = tmp_path / "blocked_parent"
    blocked_parent.write_text("not a directory", encoding="utf-8")

    with pytest.raises(OSError, match="Failed to write file|Not a directory|File exists"):
        write_text(blocked_parent / "out.txt", "x")


def test_policy_config_is_cached_and_validated() -> None:
    load_policy_thresholds.cache_clear()
    policy = load_policy_thresholds()

    assert get_high_discount_threshold() == float(policy["high_discount_threshold"])
    assert load_policy_thresholds() is policy

    with pytest.raises(ValueError, match="weights must sum"):
        _assert_weight_sum({"a": 0.4, "b": 0.5}, ["a", "b"], "test")


def test_policy_config_json_remains_parseable() -> None:
    with open("config/policy_thresholds.json", encoding="utf-8") as handle:
        policy = json.load(handle)

    assert "customer_risk_scoring" in policy
    assert 0 <= float(policy["high_discount_threshold"]) <= 1


def test_processed_validation_handles_zero_list_revenue_without_crashing() -> None:
    processed_tables = {
        "order_item_pricing_metrics": pd.DataFrame(
            {
                "order_item_id": ["OI1"],
                "order_id": ["O1"],
                "customer_id": ["C1"],
                "realized_price": [0.0],
                "discount_depth": [0.0],
                "discount_bucket": ["0-5%"],
                "margin_proxy_pct": [0.0],
                "line_revenue": [0.0],
                "line_list_revenue": [0.0],
            }
        )
    }

    report, is_valid = validate_processed_tables(processed_tables)
    reconciliation = report[
        report["check_name"] == "order_item_pricing_metrics_weighted_discount_reconciliation"
    ].iloc[0]

    assert not is_valid
    assert reconciliation["status"] == "FAIL"
    assert "total_list_revenue must be positive" in reconciliation["detail"]
