from __future__ import annotations

import pandas as pd
import pytest

from src.analysis.formal_analysis import _pricing_health_verdict
from src.ingestion.synthetic_data import SyntheticDataConfig, generate_synthetic_business_data
from src.scoring.risk_scoring import _risk_tier_from_score, _scale_excess, _scale_shortfall
from src.validation.data_quality import validate_processed_tables, validate_raw_tables


def _base_config() -> SyntheticDataConfig:
    return SyntheticDataConfig(
        seed=99,
        n_customers=50,
        n_products=28,
        n_sales_reps=5,
        n_orders=200,
        start_date="2024-01-01",
        end_date="2024-06-30",
    )


def _base_raw() -> dict:
    return generate_synthetic_business_data(_base_config())


def test_validate_raw_tables_returns_failure_on_missing_column() -> None:
    raw = _base_raw()
    raw["order_items"] = raw["order_items"].drop(columns=["discount_pct"])

    report, valid = validate_raw_tables(raw)

    assert not valid, "Validation should fail when a required column is absent"
    assert any(
        "order_items_required_columns" in row["check_name"] and row["status"] == "FAIL"
        for row in report.to_dict("records")
    ), "Expected order_items_required_columns FAIL in report"


def test_validate_processed_tables_returns_failure_on_missing_column() -> None:
    processed = {
        "order_item_pricing_metrics": pd.DataFrame(
            {
                "order_item_id": ["OI1"],
                "order_id": ["O1"],
                "customer_id": ["C1"],
                "realized_price": [90.0],
                "discount_depth": [0.1],
                "margin_proxy_pct": [0.4],
            }
        )
    }

    report, valid = validate_processed_tables(processed)

    assert not valid
    failure = report.loc[
        report["check_name"] == "order_item_pricing_metrics_required_columns"
    ].iloc[0]
    assert failure["status"] == "FAIL"
    assert "discount_bucket" in failure["detail"]


def test_validate_raw_tables_returns_failure_on_missing_table() -> None:
    raw = _base_raw()
    del raw["products"]

    report, valid = validate_raw_tables(raw)

    assert not valid
    failed = set(report.loc[report["status"] == "FAIL", "check_name"])
    assert any("products" in name for name in failed)


def test_negative_discount_caught_by_raw_validation() -> None:
    raw = _base_raw()
    raw["order_items"] = raw["order_items"].copy()
    raw["order_items"].loc[0, "discount_pct"] = -0.05
    raw["order_items"].loc[0, "realized_unit_price"] = (
        raw["order_items"].loc[0, "list_price_at_sale"] * 1.05
    )

    report, valid = validate_raw_tables(raw)

    assert not valid
    failed_names = set(report.loc[report["status"] == "FAIL", "check_name"])
    assert "order_items_discount_bounds" in failed_names


def test_zero_list_price_caught_by_raw_validation() -> None:
    raw = _base_raw()
    raw["order_items"] = raw["order_items"].copy()
    raw["order_items"].loc[0, "list_price_at_sale"] = 0.0
    raw["order_items"].loc[0, "realized_unit_price"] = 0.0

    report, valid = validate_raw_tables(raw)

    assert not valid
    failed_names = set(report.loc[report["status"] == "FAIL", "check_name"])
    assert "order_items_positive_list_price" in failed_names


def test_non_numeric_discount_returns_structured_failure() -> None:
    raw = _base_raw()
    raw["order_items"] = raw["order_items"].copy()
    raw["order_items"]["discount_pct"] = raw["order_items"]["discount_pct"].astype(object)
    raw["order_items"].loc[0, "discount_pct"] = "invalid"

    report, valid = validate_raw_tables(raw)

    assert not valid
    failed_names = set(report.loc[report["status"] == "FAIL", "check_name"])
    assert "order_items_discount_pct_numeric" in failed_names


def test_discount_formula_mismatch_caught_by_raw_validation() -> None:
    raw = _base_raw()
    raw["order_items"] = raw["order_items"].copy()
    raw["order_items"].loc[0, "discount_pct"] += 0.001

    report, valid = validate_raw_tables(raw)

    assert not valid
    failed_names = set(report.loc[report["status"] == "FAIL", "check_name"])
    assert "order_items_discount_formula_consistency" in failed_names


def test_order_before_signup_caught_by_raw_validation() -> None:
    raw = _base_raw()
    customer_id = raw["orders"].loc[0, "customer_id"]
    raw["customers"] = raw["customers"].copy()
    raw["customers"].loc[raw["customers"]["customer_id"] == customer_id, "signup_date"] = (
        pd.Timestamp("2030-01-01")
    )

    report, valid = validate_raw_tables(raw)

    assert not valid
    failed_names = set(report.loc[report["status"] == "FAIL", "check_name"])
    assert "orders_not_before_customer_signup" in failed_names


def test_synthetic_config_rejects_invalid_inputs() -> None:
    with pytest.raises(ValueError, match="n_products"):
        SyntheticDataConfig(n_products=4)
    with pytest.raises(ValueError, match="start_date"):
        SyntheticDataConfig(start_date="2025-01-01", end_date="2024-01-01")


def test_cli_rejects_products_below_minimum() -> None:
    import scripts.run_pipeline as run_pipeline

    with pytest.raises(SystemExit):
        run_pipeline.parse_args(["--products", "4"])


def test_cli_accepts_products_at_minimum() -> None:
    import scripts.run_pipeline as run_pipeline

    args = run_pipeline.parse_args(["--products", "5"])
    assert args.products == 5


def test_risk_tier_from_score_boundaries() -> None:
    assert _risk_tier_from_score(80.0) == "Critical"
    assert _risk_tier_from_score(79.9) == "High"
    assert _risk_tier_from_score(65.0) == "High"
    assert _risk_tier_from_score(64.9) == "Medium"
    assert _risk_tier_from_score(45.0) == "Medium"
    assert _risk_tier_from_score(44.9) == "Low"
    assert _risk_tier_from_score(0.0) == "Low"
    assert _risk_tier_from_score(100.0) == "Critical"


def test_scale_excess_zero_below_threshold() -> None:
    series = pd.Series([0.05, 0.10, 0.15])
    result = _scale_excess(series, threshold=0.20, max_excess=0.20)
    assert (result == 0.0).all(), "All values below threshold should score 0"


def test_scale_excess_full_at_max() -> None:
    series = pd.Series([0.40])
    result = _scale_excess(series, threshold=0.20, max_excess=0.20)
    assert float(result.iloc[0]) == pytest.approx(100.0)


def test_scale_excess_clipped_at_100() -> None:
    series = pd.Series([0.99])
    result = _scale_excess(series, threshold=0.20, max_excess=0.20)
    assert float(result.iloc[0]) == 100.0


def test_scale_shortfall_zero_above_threshold() -> None:
    series = pd.Series([0.50, 0.60])
    result = _scale_shortfall(series, threshold=0.40, max_shortfall=0.40)
    assert (result == 0.0).all()


def test_scale_shortfall_full_at_zero() -> None:
    series = pd.Series([0.00])
    result = _scale_shortfall(series, threshold=0.40, max_shortfall=0.40)
    assert float(result.iloc[0]) == pytest.approx(100.0)


def test_scale_excess_zero_max_excess_returns_zeros() -> None:
    series = pd.Series([0.99])
    result = _scale_excess(series, threshold=0.20, max_excess=0.0)
    assert (result == 0.0).all()


def _health_row(
    weighted_discount: float, high_discount_share: float, margin_proxy: float
) -> pd.Series:
    return pd.Series(
        {
            "weighted_realized_discount": weighted_discount,
            "high_discount_revenue_share": high_discount_share,
            "margin_proxy_pct": margin_proxy,
        }
    )


def test_pricing_health_verdict_healthy() -> None:
    verdict, _ = _pricing_health_verdict(_health_row(0.10, 0.15, 0.50))
    assert "Healthy" in verdict


def test_pricing_health_verdict_mixed() -> None:
    verdict, _ = _pricing_health_verdict(_health_row(0.15, 0.25, 0.42))
    assert "Mixed" in verdict


def test_pricing_health_verdict_discount_reliant() -> None:
    verdict, _ = _pricing_health_verdict(_health_row(0.30, 0.50, 0.30))
    assert "Discount-reliant" in verdict


def test_pricing_health_verdict_boundary_healthy_threshold() -> None:
    verdict, _ = _pricing_health_verdict(_health_row(0.12, 0.20, 0.45))
    assert "Healthy" in verdict


def test_synthetic_data_generates_with_minimum_products() -> None:
    cfg = SyntheticDataConfig(
        seed=1,
        n_customers=10,
        n_products=5,
        n_sales_reps=3,
        n_orders=20,
        start_date="2024-01-01",
        end_date="2024-06-30",
    )
    raw = generate_synthetic_business_data(cfg)
    assert len(raw["products"]) == 5
    assert raw["products"]["category"].nunique() == 5
    assert len(raw["order_items"]) > 0
