from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.features.pricing_features import (
    build_customer_pricing_profile,
    build_feature_tables,
    build_order_item_pricing_metrics,
)
from src.scoring.risk_scoring import score_customer_pricing_risk
from src.validation.data_quality import validate_processed_tables, validate_raw_tables


def _enriched_order_items() -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "order_item_id": "OI1",
                "order_id": "O1",
                "order_date": pd.Timestamp("2024-01-02"),
                "customer_id": "C1",
                "segment": "SMB",
                "region": "North",
                "company_size": "Small",
                "product_id": "P1",
                "sales_channel": "Online",
                "quantity": 2,
                "list_price_at_sale": 100.0,
                "realized_unit_price": 100.0,
                "discount_pct": 0.00,
                "unit_cost": 60.0,
            },
            {
                "order_item_id": "OI2",
                "order_id": "O2",
                "order_date": pd.Timestamp("2024-01-10"),
                "customer_id": "C1",
                "segment": "SMB",
                "region": "North",
                "company_size": "Small",
                "product_id": "P1",
                "sales_channel": "Online",
                "quantity": 1,
                "list_price_at_sale": 100.0,
                "realized_unit_price": 80.0,
                "discount_pct": 0.20,
                "unit_cost": 50.0,
            },
            {
                "order_item_id": "OI3",
                "order_id": "O3",
                "order_date": pd.Timestamp("2024-01-20"),
                "customer_id": "C1",
                "segment": "SMB",
                "region": "North",
                "company_size": "Small",
                "product_id": "P2",
                "sales_channel": "Field",
                "quantity": 1,
                "list_price_at_sale": 200.0,
                "realized_unit_price": 140.0,
                "discount_pct": 0.30,
                "unit_cost": 100.0,
            },
            {
                "order_item_id": "OI4",
                "order_id": "O4",
                "order_date": pd.Timestamp("2024-01-03"),
                "customer_id": "C2",
                "segment": "Enterprise",
                "region": "South",
                "company_size": "Large",
                "product_id": "P3",
                "sales_channel": "Online",
                "quantity": 1,
                "list_price_at_sale": 50.0,
                "realized_unit_price": 0.0,
                "discount_pct": 1.00,
                "unit_cost": 10.0,
            },
        ]
    )


def _raw_tables() -> dict[str, pd.DataFrame]:
    return {
        "customers": pd.DataFrame(
            [
                {
                    "customer_id": "C1",
                    "signup_date": "2024-01-01",
                    "segment": "SMB",
                    "region": "North",
                    "company_size": "Small",
                }
            ]
        ),
        "products": pd.DataFrame(
            [
                {
                    "product_id": "P1",
                    "product_name": "Product 1",
                    "category": "Core",
                    "list_price": 100.0,
                    "unit_cost": 60.0,
                }
            ]
        ),
        "orders": pd.DataFrame(
            [
                {
                    "order_id": "O1",
                    "customer_id": "C1",
                    "order_date": "2024-01-02",
                    "sales_channel": "Online",
                    "sales_rep_id": "R1",
                }
            ]
        ),
        "order_items": pd.DataFrame(
            [
                {
                    "order_item_id": "OI1",
                    "order_id": "O1",
                    "product_id": "P1",
                    "quantity": 2,
                    "list_price_at_sale": 100.0,
                    "realized_unit_price": 90.0,
                    "discount_pct": 0.10,
                }
            ]
        ),
        "sales_reps": pd.DataFrame(
            [
                {
                    "sales_rep_id": "R1",
                    "team": "A",
                    "region": "North",
                }
            ]
        ),
    }


def _risk_profile() -> pd.DataFrame:
    base = {
        "segment": "SMB",
        "region": "North",
        "company_size": "Small",
        "total_revenue": 1000.0,
        "share_orders_discounted": 1.0,
    }
    return pd.DataFrame(
        [
            {
                **base,
                "customer_id": "C_extreme",
                "total_orders": 6,
                "avg_discount_pct": 0.99,
                "share_orders_high_discount": 1.0,
                "revenue_high_discount_share": 1.0,
                "avg_margin_proxy_pct": 0.0,
                "repeat_discount_behavior": 1.0,
                "realized_price_cv": 1.0,
            },
            {
                **base,
                "customer_id": "C_clean",
                "total_orders": 6,
                "avg_discount_pct": 0.0,
                "share_orders_high_discount": 0.0,
                "revenue_high_discount_share": 0.0,
                "avg_margin_proxy_pct": 0.8,
                "repeat_discount_behavior": 0.0,
                "realized_price_cv": 0.0,
            },
        ]
    )


def _processed_tables() -> dict[str, pd.DataFrame]:
    feature_tables = build_feature_tables(_enriched_order_items())
    risk_tables = {
        "customer_risk_scores": score_customer_pricing_risk(feature_tables["customer_pricing_profile"])
    }
    return {**feature_tables, **risk_tables}


def test_order_item_pricing_metrics_handle_thresholds_and_zero_revenue() -> None:
    pricing = build_order_item_pricing_metrics(_enriched_order_items())
    by_item = pricing.set_index("order_item_id")

    assert by_item.loc["OI2", "discount_bucket"] == "10-20%"
    assert by_item.loc["OI2", "high_discount_flag"] == 1
    assert by_item.loc["OI2", "discounted_flag"] == 1
    assert by_item.loc["OI2", "line_revenue"] == pytest.approx(80.0)
    assert by_item.loc["OI2", "line_cost"] == pytest.approx(50.0)
    assert by_item.loc["OI2", "gross_margin_value"] == pytest.approx(30.0)
    assert by_item.loc["OI2", "margin_proxy_pct"] == pytest.approx(0.375)

    assert by_item.loc["OI4", "discount_bucket"] == "30%+"
    assert np.isnan(by_item.loc["OI4", "margin_proxy_pct"])
    assert by_item.loc["OI1", "realized_price_residual_pct"] == pytest.approx(10.0 / 90.0)


def test_customer_pricing_profile_reconciles_repeat_and_zero_revenue_behavior() -> None:
    pricing = build_order_item_pricing_metrics(_enriched_order_items())
    profile = build_customer_pricing_profile(pricing).set_index("customer_id")

    assert profile.loc["C1", "total_orders"] == 3
    assert profile.loc["C1", "weighted_discount_pct"] == pytest.approx(0.16)
    assert profile.loc["C1", "share_orders_high_discount"] == pytest.approx(2 / 3)
    assert profile.loc["C1", "repeat_discount_behavior"] == pytest.approx(0.5)
    assert profile.loc["C1", "revenue_high_discount_share"] == pytest.approx(220 / 420)
    assert profile.loc["C1", "avg_margin_proxy_pct"] == pytest.approx(150 / 420)

    assert profile.loc["C2", "total_revenue"] == pytest.approx(0.0)
    assert profile.loc["C2", "avg_margin_proxy_pct"] == pytest.approx(0.0)
    assert profile.loc["C2", "revenue_high_discount_share"] == pytest.approx(0.0)
    assert profile.loc["C2", "repeat_discount_behavior"] == pytest.approx(0.0)


def test_score_customer_pricing_risk_stabilizes_low_data_customers_to_neutral_score() -> None:
    low_data_profile = _risk_profile().iloc[[0]].copy()
    low_data_profile["customer_id"] = "C_low_data"
    low_data_profile["total_orders"] = 0

    scored = score_customer_pricing_risk(low_data_profile).iloc[0]

    assert scored["score_reliability_weight"] == pytest.approx(0.0)
    assert scored["low_data_flag"] == 1
    assert scored["pricing_risk_score"] == pytest.approx(50.0)
    assert scored["discount_dependency_score"] == pytest.approx(50.0)
    assert scored["margin_erosion_score"] == pytest.approx(50.0)
    assert scored["governance_priority_score"] == pytest.approx(50.0)
    assert scored["risk_tier"] == "Medium"


def test_score_customer_pricing_risk_prioritizes_extreme_policy_breaches() -> None:
    scored = score_customer_pricing_risk(_risk_profile())

    extreme = scored.iloc[0]
    clean = scored.set_index("customer_id").loc["C_clean"]

    assert extreme["customer_id"] == "C_extreme"
    assert extreme["risk_tier"] == "Critical"
    assert extreme["recommended_action"] == "investigate rep behavior"
    assert extreme["governance_priority_score"] > clean["governance_priority_score"]
    assert clean["risk_tier"] == "Low"
    assert clean["recommended_action"] == "monitor only"


def test_validate_raw_tables_catches_foreign_key_and_invalid_date_failures() -> None:
    raw_tables = _raw_tables()
    raw_tables["order_items"] = raw_tables["order_items"].copy()
    raw_tables["customers"] = raw_tables["customers"].copy()
    raw_tables["order_items"].loc[0, "product_id"] = "missing-product"
    raw_tables["customers"].loc[0, "signup_date"] = "invalid-date"

    report, is_valid = validate_raw_tables(raw_tables)
    failed = report.set_index("check_name")

    assert not is_valid
    assert failed.loc["order_items_product_fk", "status"] == "FAIL"
    assert failed.loc["order_items_product_fk", "failed_rows"] == 1
    assert failed.loc["customer_and_order_dates_valid", "status"] == "FAIL"
    assert failed.loc["customer_and_order_dates_valid", "failed_rows"] == 1


def test_validate_raw_tables_catches_empty_required_tables() -> None:
    raw_tables = _raw_tables()
    raw_tables["orders"] = raw_tables["orders"].iloc[0:0].copy()

    report, is_valid = validate_raw_tables(raw_tables)
    failed = report.set_index("check_name")

    assert not is_valid
    assert failed.loc["orders_row_count_gate", "status"] == "FAIL"
    assert failed.loc["orders_row_count_gate", "failed_rows"] == 1
    assert failed.loc["order_items_order_fk", "status"] == "FAIL"


def test_validate_processed_tables_catches_pricing_reconciliation_failures() -> None:
    processed_tables = _processed_tables()
    processed_tables["order_item_pricing_metrics"] = processed_tables["order_item_pricing_metrics"].copy()
    processed_tables["order_item_pricing_metrics"].loc[0, "line_revenue"] += 25.0

    report, is_valid = validate_processed_tables(processed_tables)
    failed = report.set_index("check_name")

    assert not is_valid
    assert failed.loc["order_item_pricing_metrics_line_revenue_formula", "status"] == "FAIL"
    assert failed.loc["order_item_pricing_metrics_weighted_discount_reconciliation", "status"] == "FAIL"


def test_validate_processed_tables_catches_invalid_risk_taxonomy_values() -> None:
    processed_tables = _processed_tables()
    processed_tables["customer_risk_scores"] = processed_tables["customer_risk_scores"].copy()
    processed_tables["customer_risk_scores"].loc[0, "risk_tier"] = "Severe"
    processed_tables["customer_risk_scores"].loc[0, "recommended_action"] = "manual override"

    report, is_valid = validate_processed_tables(processed_tables)
    failed = report.set_index("check_name")

    assert not is_valid
    assert failed.loc["customer_risk_scores_allowed_tiers", "status"] == "FAIL"
    assert failed.loc["customer_risk_scores_allowed_actions", "status"] == "FAIL"
