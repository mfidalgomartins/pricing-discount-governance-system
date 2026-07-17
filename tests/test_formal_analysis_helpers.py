from __future__ import annotations

import numpy as np
import pandas as pd

from src.analysis.formal_analysis import (
    _build_governance_action_queue,
    _discount_dependency,
    _margin_erosion_risk,
)
from src.utils.policy import get_high_discount_threshold


def _make_pricing(n: int = 20, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    categories = ["Electronics", "Software", "Hardware"]
    segments = ["Enterprise", "SMB"]
    regions = ["EMEA", "AMER"]
    teams = ["Direct", "Channel"]

    discount_depths = rng.uniform(0.05, 0.40, n)
    line_revenue = rng.uniform(500, 5000, n)
    line_list_revenue = line_revenue * rng.uniform(1.0, 1.5, n)
    gross_margin = rng.uniform(100, 2000, n)

    return pd.DataFrame(
        {
            "order_item_id": range(n),
            "customer_id": [f"C{i % 4:03d}" for i in range(n)],
            "product_id": [f"P{i % 3:03d}" for i in range(n)],
            "product_name": [f"Product {i % 3}" for i in range(n)],
            "category": [categories[i % 3] for i in range(n)],
            "segment": [segments[i % 2] for i in range(n)],
            "region": [regions[i % 2] for i in range(n)],
            "sales_rep_id": [f"R{i % 2:03d}" for i in range(n)],
            "team": [teams[i % 2] for i in range(n)],
            "rep_region": [regions[i % 2] for i in range(n)],
            "discount_depth": discount_depths,
            "line_revenue": line_revenue,
            "line_list_revenue": line_list_revenue,
            "gross_margin_value": gross_margin,
            "margin_proxy_pct": gross_margin / line_revenue,
            "high_discount_flag": (discount_depths >= get_high_discount_threshold()).astype(int),
            "year": 2024,
        }
    )


def _make_customer_profile(pricing: pd.DataFrame) -> pd.DataFrame:
    return pricing.groupby("customer_id", as_index=False).agg(
        segment=("segment", "first"),
        region=("region", "first"),
        total_revenue=("line_revenue", "sum"),
        revenue_high_discount_share=("high_discount_flag", "mean"),
        repeat_discount_behavior=("high_discount_flag", "mean"),
        share_orders_discounted=("high_discount_flag", "mean"),
    )


def _make_risk_scores(customer_profile: pd.DataFrame) -> pd.DataFrame:
    n = len(customer_profile)
    rng = np.random.default_rng(0)
    scores = customer_profile[["customer_id", "segment", "region", "total_revenue"]].copy()
    scores["governance_priority_score"] = rng.uniform(20, 90, n)
    scores["risk_tier"] = [
        "High" if s > 65 else "Medium" for s in scores["governance_priority_score"]
    ]
    scores["main_risk_driver"] = "discount_dependency"
    scores["recommended_action"] = "Review"
    return scores


class TestBuildGovernanceActionQueue:
    def test_returns_empty_on_none_risk_scores(self) -> None:
        pricing = _make_pricing()
        result = _build_governance_action_queue(pricing, None)
        assert isinstance(result, pd.DataFrame)
        assert result.empty

    def test_returns_empty_on_empty_risk_scores(self) -> None:
        pricing = _make_pricing()
        result = _build_governance_action_queue(pricing, pd.DataFrame())
        assert result.empty

    def test_output_has_required_columns(self) -> None:
        pricing = _make_pricing()
        cp = _make_customer_profile(pricing)
        rs = _make_risk_scores(cp)
        result = _build_governance_action_queue(pricing, rs)
        required = {
            "customer_id",
            "segment",
            "region",
            "risk_tier",
            "governance_priority_score",
            "priority_value_proxy",
            "high_discount_revenue",
            "margin_at_risk_revenue",
        }
        assert required.issubset(result.columns)

    def test_sorted_by_priority_value_descending(self) -> None:
        pricing = _make_pricing()
        cp = _make_customer_profile(pricing)
        rs = _make_risk_scores(cp)
        result = _build_governance_action_queue(pricing, rs)
        pvp = result["priority_value_proxy"].tolist()
        assert pvp == sorted(pvp, reverse=True)

    def test_no_negative_derived_columns(self) -> None:
        pricing = _make_pricing()
        cp = _make_customer_profile(pricing)
        rs = _make_risk_scores(cp)
        result = _build_governance_action_queue(pricing, rs)
        assert (result["high_discount_revenue"] >= 0).all()
        assert (result["margin_at_risk_revenue"] >= 0).all()


class TestDiscountDependency:
    def test_returns_four_tables(self) -> None:
        pricing = _make_pricing()
        cp = _make_customer_profile(pricing)
        result = _discount_dependency(pricing, cp)
        assert set(result.keys()) == {
            "customer_discount_dependency",
            "segment_discount_dependency",
            "product_discount_dependency",
            "discount_dependency_concentration",
        }

    def test_concentration_table_has_one_row(self) -> None:
        pricing = _make_pricing()
        cp = _make_customer_profile(pricing)
        result = _discount_dependency(pricing, cp)
        assert len(result["discount_dependency_concentration"]) == 1

    def test_segment_dependency_covers_all_segments(self) -> None:
        pricing = _make_pricing()
        cp = _make_customer_profile(pricing)
        result = _discount_dependency(pricing, cp)
        expected_segments = set(pricing["segment"].unique())
        actual_segments = set(result["segment_discount_dependency"]["segment"].unique())
        assert expected_segments == actual_segments

    def test_high_discount_revenue_share_between_0_and_1(self) -> None:
        pricing = _make_pricing()
        cp = _make_customer_profile(pricing)
        result = _discount_dependency(pricing, cp)
        share = result["product_discount_dependency"]["high_discount_revenue_share"].dropna()
        assert (share >= 0).all() and (share <= 1).all()


class TestMarginErosionRisk:
    def test_returns_dataframe(self) -> None:
        pricing = _make_pricing()
        result = _margin_erosion_risk(pricing)
        assert isinstance(result, pd.DataFrame)
        assert len(result) > 0

    def test_has_margin_erosion_risk_score(self) -> None:
        pricing = _make_pricing()
        result = _margin_erosion_risk(pricing)
        assert "margin_erosion_risk_score" in result.columns

    def test_score_between_0_and_100(self) -> None:
        pricing = _make_pricing()
        result = _margin_erosion_risk(pricing)
        scores = result["margin_erosion_risk_score"].dropna()
        assert (scores >= 0).all() and (scores <= 100).all()

    def test_sorted_by_score_descending(self) -> None:
        pricing = _make_pricing()
        result = _margin_erosion_risk(pricing)
        scores = result["margin_erosion_risk_score"].tolist()
        assert scores == sorted(scores, reverse=True)

    def test_discount_leakage_value_non_negative(self) -> None:
        pricing = _make_pricing(n=30)
        pricing = pricing.copy()
        pricing["line_list_revenue"] = pricing["line_revenue"] * 1.2
        result = _margin_erosion_risk(pricing)
        assert (result["discount_leakage_value"] >= -1e-9).all()
