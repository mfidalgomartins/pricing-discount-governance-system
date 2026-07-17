from __future__ import annotations

import json

import pandas as pd
import pytest

from src.utils.io import (
    _as_path,
    _validate_table_name,
    read_csv,
    write_csv,
    write_table_bundle,
    write_text,
)
from src.utils.policy import (
    _assert_weight_sum,
    _validate_dashboard_policy,
    get_discounted_threshold,
    get_high_discount_threshold,
    get_margin_at_risk_proxy_max,
    load_dashboard_policy,
    load_policy_thresholds,
)
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

    with pytest.raises(OSError, match=r"Failed to write file|Not a directory|File exists"):
        write_text(blocked_parent / "out.txt", "x")


def test_io_type_guards_reject_wrong_types(tmp_path) -> None:
    with pytest.raises(TypeError, match="df must be a pandas DataFrame"):
        write_csv(["not", "a", "frame"], tmp_path / "out.csv")

    with pytest.raises(TypeError, match="content must be str"):
        write_text(tmp_path / "out.txt", 123)

    with pytest.raises(TypeError, match="path must be str or Path"):
        _as_path(123)

    with pytest.raises(TypeError, match="tables must be a dict"):
        write_table_bundle([pd.DataFrame({"a": [1]})], tmp_path / "bundle")


def test_read_csv_missing_file_raises_contextual_error(tmp_path) -> None:
    with pytest.raises(FileNotFoundError, match="CSV file not found"):
        read_csv(tmp_path / "does_not_exist.csv")


def test_write_table_bundle_rejects_unsafe_table_names(tmp_path) -> None:
    # A table name with path separators must be rejected before any file is written,
    # blocking directory traversal via crafted bundle keys.
    with pytest.raises(ValueError, match="letters, numbers, underscores"):
        write_table_bundle({"../escape": pd.DataFrame({"a": [1]})}, tmp_path / "bundle")

    for bad_name in ("../escape", "sub/dir", "name with space", ""):
        with pytest.raises(ValueError, match="letters, numbers, underscores"):
            _validate_table_name(bad_name)

    # A well-formed name passes silently.
    _validate_table_name("order_item-metrics_2024")


def test_policy_config_is_cached_and_validated() -> None:
    load_policy_thresholds.cache_clear()
    load_dashboard_policy.cache_clear()
    policy = load_policy_thresholds()
    dashboard_policy = load_dashboard_policy()

    assert get_high_discount_threshold() == float(policy["high_discount_threshold"])
    assert get_discounted_threshold() == float(policy["discounted_threshold"])
    assert get_margin_at_risk_proxy_max() == float(policy["margin_at_risk_proxy_max"])
    assert load_policy_thresholds() is policy
    assert load_dashboard_policy() is dashboard_policy

    with pytest.raises(ValueError, match="weights must sum"):
        _assert_weight_sum({"a": 0.4, "b": 0.5}, ["a", "b"], "test")


def test_dashboard_policy_rejects_missing_and_misordered_thresholds() -> None:
    valid_thresholds = load_dashboard_policy()["thresholds"].copy()

    missing_threshold = {"thresholds": valid_thresholds.copy()}
    del missing_threshold["thresholds"]["high_risk_count_warn"]
    with pytest.raises(ValueError, match="missing"):
        _validate_dashboard_policy(missing_threshold)

    misordered_thresholds = {"thresholds": valid_thresholds.copy()}
    misordered_thresholds["thresholds"]["weighted_discount_warn"] = 0.25
    with pytest.raises(ValueError, match="warning must be below critical"):
        _validate_dashboard_policy(misordered_thresholds)


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
                "product_id": ["P1"],
                "sales_channel": ["Direct"],
                "quantity": [1],
                "realized_price": [0.0],
                "list_price_at_sale": [0.0],
                "unit_cost": [0.0],
                "discount_depth": [0.0],
                "discount_bucket": ["0-5%"],
                "line_revenue": [0.0],
                "line_list_revenue": [0.0],
                "line_cost": [0.0],
                "gross_margin_value": [0.0],
                "margin_proxy_pct": [float("nan")],
                "line_price_realization": [float("nan")],
                "price_realization_residual_pct": [0.0],
                "abs_price_realization_residual_pct": [0.0],
                "high_discount_flag": [0],
                "discounted_flag": [0],
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
