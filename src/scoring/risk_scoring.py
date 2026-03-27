from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd


def _percentile_score(series: pd.Series, higher_is_risk: bool = True) -> pd.Series:
    ranked = series.rank(method="average", pct=True)
    score = ranked * 100
    if not higher_is_risk:
        score = (1 - ranked) * 100
    return score.clip(0, 100)


def _risk_tier_from_score(score: float) -> str:
    if score >= 80:
        return "Critical"
    if score >= 65:
        return "High"
    if score >= 45:
        return "Medium"
    return "Low"


def _recommended_action(row: pd.Series) -> str:
    driver_action_map = {
        "pricing_risk_score": "investigate rep behavior",
        "discount_dependency_score": "redesign discount policy",
        "margin_erosion_score": "tighten approval thresholds",
    }

    if row["risk_tier"] == "Low":
        return "monitor only"
    if row["risk_tier"] == "Medium":
        return "review segment pricing"

    return driver_action_map.get(row["main_risk_driver"], "review segment pricing")


def score_customer_pricing_risk(customer_profile: pd.DataFrame) -> pd.DataFrame:
    scored = customer_profile.copy()

    discount_depth_score = _percentile_score(scored["avg_discount_pct"], higher_is_risk=True)
    variability_score = _percentile_score(scored["realized_price_cv"], higher_is_risk=True)
    discount_share_score = _percentile_score(scored["share_orders_high_discount"], higher_is_risk=True)
    high_discount_revenue_score = _percentile_score(scored["revenue_high_discount_share"], higher_is_risk=True)
    repeat_behavior_score = _percentile_score(scored["repeat_discount_behavior"], higher_is_risk=True)
    margin_erosion_component = _percentile_score(scored["avg_margin_proxy_pct"], higher_is_risk=False)

    scored["pricing_risk_score"] = (
        0.50 * discount_depth_score + 0.30 * variability_score + 0.20 * discount_share_score
    )
    scored["discount_dependency_score"] = (
        0.45 * high_discount_revenue_score + 0.35 * repeat_behavior_score + 0.20 * discount_share_score
    )
    scored["margin_erosion_score"] = (
        0.55 * margin_erosion_component + 0.30 * discount_depth_score + 0.15 * high_discount_revenue_score
    )

    scored["governance_priority_score"] = (
        0.40 * scored["pricing_risk_score"]
        + 0.35 * scored["discount_dependency_score"]
        + 0.25 * scored["margin_erosion_score"]
    )

    score_columns = [
        "pricing_risk_score",
        "discount_dependency_score",
        "margin_erosion_score",
        "governance_priority_score",
    ]
    scored[score_columns] = scored[score_columns].round(2)

    scored["risk_tier"] = scored["governance_priority_score"].apply(_risk_tier_from_score)
    scored["main_risk_driver"] = scored[
        ["pricing_risk_score", "discount_dependency_score", "margin_erosion_score"]
    ].idxmax(axis=1)
    scored["recommended_action"] = scored.apply(_recommended_action, axis=1)

    ordered_columns = [
        "customer_id",
        "segment",
        "region",
        "company_size",
        "total_orders",
        "total_revenue",
        "avg_discount_pct",
        "share_orders_discounted",
        "share_orders_high_discount",
        "revenue_high_discount_share",
        "avg_margin_proxy_pct",
        "pricing_risk_score",
        "discount_dependency_score",
        "margin_erosion_score",
        "governance_priority_score",
        "risk_tier",
        "main_risk_driver",
        "recommended_action",
    ]

    return scored[ordered_columns].sort_values("governance_priority_score", ascending=False).reset_index(drop=True)


def build_risk_outputs(feature_tables: Dict[str, pd.DataFrame]) -> Dict[str, pd.DataFrame]:
    customer_profile = feature_tables["customer_pricing_profile"]
    customer_risk_scores = score_customer_pricing_risk(customer_profile)

    risk_tier_summary = (
        customer_risk_scores.groupby(["risk_tier", "recommended_action"], as_index=False)
        .agg(
            customers=("customer_id", "count"),
            total_revenue=("total_revenue", "sum"),
            avg_governance_priority=("governance_priority_score", "mean"),
        )
        .sort_values(["risk_tier", "total_revenue"], ascending=[True, False])
    )

    main_driver_summary = (
        customer_risk_scores.groupby("main_risk_driver", as_index=False)
        .agg(
            customers=("customer_id", "count"),
            total_revenue=("total_revenue", "sum"),
            avg_priority=("governance_priority_score", "mean"),
        )
        .sort_values("avg_priority", ascending=False)
    )

    return {
        "customer_risk_scores": customer_risk_scores,
        "risk_tier_summary": risk_tier_summary,
        "main_driver_summary": main_driver_summary,
    }
