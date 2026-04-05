from __future__ import annotations

from typing import Dict

import numpy as np
import pandas as pd


AVG_DISCOUNT_POLICY_THRESHOLD = 0.18
HIGH_DISCOUNT_ORDER_SHARE_THRESHOLD = 0.35
HIGH_DISCOUNT_REVENUE_SHARE_THRESHOLD = 0.40
REPEAT_DISCOUNT_BEHAVIOR_THRESHOLD = 0.20
MARGIN_PROXY_FLOOR_THRESHOLD = 0.38
REALIZED_PRICE_CV_THRESHOLD = 0.45

MIN_RELIABLE_ORDER_COUNT = 6
NEUTRAL_SCORE = 50.0


def _percentile_score(series: pd.Series, higher_is_risk: bool = True) -> pd.Series:
    ranked = series.rank(method="average", pct=True)
    score = ranked * 100
    if not higher_is_risk:
        score = (1 - ranked) * 100
    return score.clip(0, 100)


def _scale_excess(series: pd.Series, threshold: float, max_excess: float) -> pd.Series:
    if max_excess <= 0:
        return pd.Series(np.zeros(len(series)), index=series.index)
    return (((series - threshold).clip(lower=0)) / max_excess * 100).clip(0, 100)


def _scale_shortfall(series: pd.Series, threshold: float, max_shortfall: float) -> pd.Series:
    if max_shortfall <= 0:
        return pd.Series(np.zeros(len(series)), index=series.index)
    return (((threshold - series).clip(lower=0)) / max_shortfall * 100).clip(0, 100)


def _stabilize_with_reliability(raw_score: pd.Series, reliability_weight: pd.Series) -> pd.Series:
    return (reliability_weight * raw_score) + ((1 - reliability_weight) * NEUTRAL_SCORE)


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

    scored["score_reliability_weight"] = (scored["total_orders"] / MIN_RELIABLE_ORDER_COUNT).clip(lower=0, upper=1)
    scored["low_data_flag"] = (scored["total_orders"] < MIN_RELIABLE_ORDER_COUNT).astype(int)

    # Relative components detect peer-level outliers.
    rel_discount_depth = _percentile_score(scored["avg_discount_pct"], higher_is_risk=True)
    rel_variability = _percentile_score(scored["realized_price_cv"], higher_is_risk=True)
    rel_discount_share = _percentile_score(scored["share_orders_high_discount"], higher_is_risk=True)
    rel_high_discount_revenue = _percentile_score(scored["revenue_high_discount_share"], higher_is_risk=True)
    rel_repeat_behavior = _percentile_score(scored["repeat_discount_behavior"], higher_is_risk=True)
    rel_margin_erosion = _percentile_score(scored["avg_margin_proxy_pct"], higher_is_risk=False)

    # Absolute components detect policy breaches regardless of peer distribution.
    abs_discount_depth = _scale_excess(scored["avg_discount_pct"], AVG_DISCOUNT_POLICY_THRESHOLD, 0.20)
    abs_variability = _scale_excess(scored["realized_price_cv"], REALIZED_PRICE_CV_THRESHOLD, 0.55)
    abs_high_discount_order_share = _scale_excess(
        scored["share_orders_high_discount"], HIGH_DISCOUNT_ORDER_SHARE_THRESHOLD, 0.65
    )
    abs_high_discount_revenue_share = _scale_excess(
        scored["revenue_high_discount_share"], HIGH_DISCOUNT_REVENUE_SHARE_THRESHOLD, 0.60
    )
    abs_repeat_behavior = _scale_excess(scored["repeat_discount_behavior"], REPEAT_DISCOUNT_BEHAVIOR_THRESHOLD, 0.80)
    abs_margin_shortfall = _scale_shortfall(scored["avg_margin_proxy_pct"], MARGIN_PROXY_FLOOR_THRESHOLD, 0.38)

    raw_pricing_risk = (
        0.60 * (0.50 * rel_discount_depth + 0.30 * rel_variability + 0.20 * rel_discount_share)
        + 0.40 * (0.45 * abs_discount_depth + 0.30 * abs_variability + 0.25 * abs_high_discount_order_share)
    )
    raw_discount_dependency = (
        0.55 * (0.45 * rel_high_discount_revenue + 0.35 * rel_repeat_behavior + 0.20 * rel_discount_share)
        + 0.45 * (
            0.45 * abs_high_discount_revenue_share
            + 0.30 * abs_repeat_behavior
            + 0.25 * abs_high_discount_order_share
        )
    )
    raw_margin_erosion = (
        0.50 * (0.55 * rel_margin_erosion + 0.30 * rel_discount_depth + 0.15 * rel_high_discount_revenue)
        + 0.50 * (
            0.55 * abs_margin_shortfall + 0.25 * abs_discount_depth + 0.20 * abs_high_discount_revenue_share
        )
    )

    scored["pricing_risk_score"] = _stabilize_with_reliability(raw_pricing_risk, scored["score_reliability_weight"])
    scored["discount_dependency_score"] = _stabilize_with_reliability(
        raw_discount_dependency, scored["score_reliability_weight"]
    )
    scored["margin_erosion_score"] = _stabilize_with_reliability(
        raw_margin_erosion, scored["score_reliability_weight"]
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
    scored["score_reliability_weight"] = scored["score_reliability_weight"].round(2)

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
        "score_reliability_weight",
        "low_data_flag",
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
