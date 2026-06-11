from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.analysis.data_profiling import _profile_single_table
from src.features.pricing_features import build_feature_tables
from src.ingestion.load_raw import save_raw_tables
from src.ingestion.synthetic_data import SyntheticDataConfig, generate_synthetic_business_data
from src.processing.build_base_tables import build_order_item_enriched
from src.processing.sql_warehouse import SqlLayerRunConfig, run_sql_warehouse_models
from src.scoring.risk_scoring import build_risk_outputs
from src.utils.paths import PROJECT_ROOT
from src.utils.policy import get_high_discount_threshold
from src.validation.data_quality import validate_processed_tables, validate_raw_tables


def _small_config() -> SyntheticDataConfig:
    return SyntheticDataConfig(
        seed=7,
        n_customers=120,
        n_products=14,
        n_sales_reps=12,
        n_orders=1100,
        start_date="2023-01-01",
        end_date="2024-12-31",
    )


def test_raw_data_validation_passes() -> None:
    raw_tables = generate_synthetic_business_data(_small_config())
    report, is_valid = validate_raw_tables(raw_tables)

    assert is_valid, f"Raw validation failed:\n{report[report['status'] == 'FAIL']}"
    assert len(raw_tables["order_items"]) > len(raw_tables["orders"])
    assert raw_tables["order_items"]["discount_pct"].between(0, 0.7).all()
    assert raw_tables["products"]["category"].nunique() == 5

    order_dates = raw_tables["orders"].merge(
        raw_tables["customers"][["customer_id", "signup_date"]],
        on="customer_id",
        validate="many_to_one",
    )
    assert (order_dates["order_date"] >= order_dates["signup_date"]).all()


def test_processed_tables_validation_passes() -> None:
    raw_tables = generate_synthetic_business_data(_small_config())
    enriched = build_order_item_enriched(raw_tables)
    feature_tables = build_feature_tables(enriched)
    risk_tables = build_risk_outputs(feature_tables)

    processed_tables = {"order_item_enriched": enriched, **feature_tables, **risk_tables}
    report, is_valid = validate_processed_tables(processed_tables)

    assert is_valid, f"Processed validation failed:\n{report[report['status'] == 'FAIL']}"
    assert processed_tables["customer_pricing_profile"]["customer_id"].is_unique


def test_order_item_enrichment_rejects_duplicate_dimension_key() -> None:
    raw_tables = generate_synthetic_business_data(_small_config())
    raw_tables["customers"] = pd.concat(
        [raw_tables["customers"], raw_tables["customers"].head(1)],
        ignore_index=True,
    )

    with pytest.raises(Exception, match="many-to-one|not unique"):
        build_order_item_enriched(raw_tables)


def test_order_item_enrichment_rejects_missing_fk() -> None:
    raw_tables = generate_synthetic_business_data(_small_config())
    raw_tables["order_items"].loc[0, "order_id"] = "missing-order"

    with pytest.raises(ValueError, match="Merge integrity failed for orders"):
        build_order_item_enriched(raw_tables)


def test_risk_scores_bounds_and_actions() -> None:
    raw_tables = generate_synthetic_business_data(_small_config())
    enriched = build_order_item_enriched(raw_tables)
    feature_tables = build_feature_tables(enriched)
    customer_risk = build_risk_outputs(feature_tables)["customer_risk_scores"]

    for col in [
        "pricing_risk_score",
        "discount_dependency_score",
        "margin_erosion_score",
        "governance_priority_score",
    ]:
        assert customer_risk[col].between(0, 100).all(), f"{col} out of bounds"

    expected_actions = {
        "tighten approval thresholds",
        "review segment pricing",
        "investigate rep behavior",
        "redesign discount policy",
        "monitor only",
    }
    assert set(customer_risk["recommended_action"]).issubset(expected_actions)
    assert customer_risk["score_reliability_weight"].between(0, 1).all()
    assert set(customer_risk["low_data_flag"].unique()).issubset({0, 1})


def test_weighted_discount_and_margin_consistency() -> None:
    raw_tables = generate_synthetic_business_data(_small_config())
    enriched = build_order_item_enriched(raw_tables)
    pricing = build_feature_tables(enriched)["order_item_pricing_metrics"]

    total_revenue = float(pricing["line_revenue"].sum())
    total_list_revenue = float(pricing["line_list_revenue"].sum())
    total_margin = float(pricing["gross_margin_value"].sum())

    weighted_discount_direct = float(np.average(pricing["discount_depth"], weights=pricing["line_list_revenue"]))
    weighted_discount_from_totals = float(1 - total_revenue / total_list_revenue)
    assert abs(weighted_discount_direct - weighted_discount_from_totals) <= 1e-5

    weighted_margin_direct = float(np.average(pricing["margin_proxy_pct"], weights=pricing["line_revenue"]))
    weighted_margin_from_totals = float(total_margin / total_revenue)
    assert abs(weighted_margin_direct - weighted_margin_from_totals) <= 1e-9


def test_customer_and_segment_margin_are_revenue_weighted() -> None:
    raw_tables = generate_synthetic_business_data(_small_config())
    enriched = build_order_item_enriched(raw_tables)
    features = build_feature_tables(enriched)
    pricing = features["order_item_pricing_metrics"]

    for grain, table_name in [
        ("customer_id", "customer_pricing_profile"),
        ("segment", "segment_pricing_summary"),
    ]:
        expected = (
            pricing.groupby(grain, as_index=False)
            .agg(revenue=("line_revenue", "sum"), margin=("gross_margin_value", "sum"))
        )
        expected["expected_margin_proxy_pct"] = expected["margin"] / expected["revenue"]
        actual = features[table_name].merge(
            expected[[grain, "expected_margin_proxy_pct"]],
            on=grain,
            validate="one_to_one",
        )
        assert np.allclose(actual["avg_margin_proxy_pct"], actual["expected_margin_proxy_pct"])


def test_profiling_allows_signed_residual_metrics() -> None:
    frame = pd.DataFrame(
        {
            "order_item_id": ["OI1", "OI2"],
            "realized_price_residual_pct": [-0.10, 0.10],
        }
    )

    issues = _profile_single_table("order_item_pricing_metrics", frame)["issues"]

    assert issues.empty or not (
        (issues["column_name"] == "realized_price_residual_pct")
        & (issues["issue_type"] == "impossible_negative_value")
    ).any()


def test_sql_warehouse_layer_execution(tmp_path) -> None:
    config = SyntheticDataConfig(
        seed=11,
        n_customers=60,
        n_products=28,
        n_sales_reps=8,
        n_orders=240,
        start_date="2024-01-01",
        end_date="2024-12-31",
    )
    raw_tables = generate_synthetic_business_data(config)
    raw_dir = tmp_path / "raw"
    save_raw_tables(raw_tables, raw_dir)

    sql_outputs = run_sql_warehouse_models(
        SqlLayerRunConfig(
            raw_dir=raw_dir,
            sql_dir=PROJECT_ROOT / "sql",
            db_path=tmp_path / "warehouse.duckdb",
            marts_output_dir=tmp_path / "sql_marts",
            outputs_dir=tmp_path / "outputs",
        )
    )

    sql_validation = sql_outputs["sql_validation_report"]
    assert not sql_validation.empty
    assert bool((sql_validation["status"] == "PASS").all())
    assert (tmp_path / "sql_marts" / "mart_customer_pricing_profile.csv").exists()

    enriched = build_order_item_enriched(raw_tables)
    pricing = build_feature_tables(enriched)["order_item_pricing_metrics"]
    sql_customer = sql_outputs["mart_customer_pricing_profile"]
    sql_overall = sql_outputs["mart_overall_pricing_health"].iloc[0]

    assert int(sql_validation.loc[sql_validation["check_name"] == "int_order_item_enriched_no_silent_drops", "status"].eq("PASS").iloc[0])
    assert len(sql_customer) == pricing["customer_id"].nunique()
    assert float(sql_overall["total_revenue"]) == pytest.approx(float(pricing["line_revenue"].sum()), rel=1e-9)
    assert float(sql_overall["weighted_realized_discount"]) == pytest.approx(
        float(np.average(pricing["discount_depth"], weights=pricing["line_list_revenue"])),
        rel=1e-4,
    )
    high_discount_revenue = pricing.loc[
        pricing["discount_depth"] >= get_high_discount_threshold(),
        "line_revenue",
    ].sum()
    assert float(sql_overall["high_discount_revenue_share"]) == pytest.approx(
        float(high_discount_revenue / pricing["line_revenue"].sum()),
        rel=1e-9,
    )
    assert str(sql_overall["as_of_date"])[:10] == pricing["order_date"].max().strftime("%Y-%m-%d")

    pandas_customer = build_feature_tables(enriched)["customer_pricing_profile"]
    customer_parity = sql_customer.merge(
        pandas_customer[["customer_id", "avg_margin_proxy_pct", "revenue_high_discount_share"]],
        on="customer_id",
        suffixes=("_sql", "_pandas"),
        validate="one_to_one",
    )
    assert np.allclose(customer_parity["avg_margin_proxy_pct_sql"], customer_parity["avg_margin_proxy_pct_pandas"])
    assert np.allclose(
        customer_parity["revenue_high_discount_share_sql"],
        customer_parity["revenue_high_discount_share_pandas"],
    )
