from __future__ import annotations

import pytest
import pandas as pd
import numpy as np

from src.ingestion.synthetic_data import generate_synthetic_business_data, SyntheticDataConfig
from src.validation.data_quality import validate_raw_tables
from src.scoring.risk_scoring import _risk_tier_from_score, _scale_excess, _scale_shortfall
from src.analysis.formal_analysis import _pricing_health_verdict


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


# ---------------------------------------------------------------------------
# CR-1: validate_raw_tables must not crash when a required column is missing
# ---------------------------------------------------------------------------

def test_validate_raw_tables_returns_failure_on_missing_column() -> None:
    raw = _base_raw()
    raw["order_items"] = raw["order_items"].drop(columns=["discount_pct"])

    # Must return a structured result — NOT raise KeyError
    report, valid = validate_raw_tables(raw)

    assert not valid, "Validation should fail when a required column is absent"
    assert any(
        "order_items_required_columns" in row["check_name"] and row["status"] == "FAIL"
        for row in report.to_dict("records")
    ), "Expected order_items_required_columns FAIL in report"


def test_validate_raw_tables_returns_failure_on_missing_table() -> None:
    raw = _base_raw()
    del raw["products"]

    report, valid = validate_raw_tables(raw)

    assert not valid
    failed = set(report.loc[report["status"] == "FAIL", "check_name"])
    assert any("products" in name for name in failed)


# ---------------------------------------------------------------------------
# CR-2: negative discount caught by raw validation
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# CR-2: zero list price caught by raw validation
# ---------------------------------------------------------------------------

def test_zero_list_price_caught_by_raw_validation() -> None:
    raw = _base_raw()
    raw["order_items"] = raw["order_items"].copy()
    raw["order_items"].loc[0, "list_price_at_sale"] = 0.0
    raw["order_items"].loc[0, "realized_unit_price"] = 0.0

    report, valid = validate_raw_tables(raw)

    assert not valid
    failed_names = set(report.loc[report["status"] == "FAIL", "check_name"])
    assert "order_items_positive_list_price" in failed_names


# ---------------------------------------------------------------------------
# CR-2: n_products < 5 guard in CLI
# ---------------------------------------------------------------------------

def test_cli_rejects_products_below_minimum() -> None:
    import scripts.run_pipeline as run_pipeline

    with pytest.raises(SystemExit):
        run_pipeline.parse_args(["--products", "4"])


def test_cli_accepts_products_at_minimum() -> None:
    import scripts.run_pipeline as run_pipeline

    args = run_pipeline.parse_args(["--products", "5"])
    assert args.products == 5


# ---------------------------------------------------------------------------
# Unit tests for pure scoring helpers (HV-3)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Unit tests for pricing health verdict (HV-3)
# ---------------------------------------------------------------------------

def _health_row(weighted_discount: float, high_discount_share: float, margin_proxy: float) -> pd.Series:
    return pd.Series({
        "weighted_realized_discount": weighted_discount,
        "high_discount_revenue_share": high_discount_share,
        "margin_proxy_pct": margin_proxy,
    })


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
    # Exactly at the healthy boundary — should be Healthy
    verdict, _ = _pricing_health_verdict(_health_row(0.12, 0.20, 0.45))
    assert "Healthy" in verdict


# ---------------------------------------------------------------------------
# CR-2: synthetic data generator survives n_products=5
# ---------------------------------------------------------------------------

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
    assert len(raw["order_items"]) > 0
