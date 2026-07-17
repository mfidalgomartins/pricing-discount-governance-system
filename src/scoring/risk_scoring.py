from __future__ import annotations

import numpy as np
import pandas as pd

from src.utils.policy import load_policy_thresholds

_POLICY = load_policy_thresholds()["customer_risk_scoring"]

WEIGHTED_DISCOUNT_POLICY_THRESHOLD = float(_POLICY["weighted_discount_policy_threshold"])
HIGH_DISCOUNT_ORDER_SHARE_THRESHOLD = float(_POLICY["high_discount_order_share_threshold"])
HIGH_DISCOUNT_REVENUE_SHARE_THRESHOLD = float(_POLICY["high_discount_revenue_share_threshold"])
REPEAT_DISCOUNT_BEHAVIOR_THRESHOLD = float(_POLICY["repeat_discount_behavior_threshold"])
MARGIN_PROXY_FLOOR_THRESHOLD = float(_POLICY["margin_proxy_floor_threshold"])
PRICE_REALIZATION_RESIDUAL_ABS_MEAN_THRESHOLD = float(
    _POLICY["price_realization_residual_abs_mean_threshold"]
)

MIN_RELIABLE_ORDER_COUNT = int(_POLICY["min_reliable_order_count"])
NEUTRAL_SCORE = float(_POLICY["neutral_score"])
RISK_TIER_THRESHOLDS = _POLICY["risk_tiers"]
PRIORITY_WEIGHTS = _POLICY["weights"]["governance_priority"]
_W_PRICING = _POLICY["weights"]["pricing_risk"]
_W_DEPENDENCY = _POLICY["weights"]["discount_dependency"]
_W_MARGIN = _POLICY["weights"]["margin_erosion"]
_SCALING_RANGES = _POLICY["scaling_ranges"]


def _percentile_score(series: pd.Series, higher_is_risk: bool = True) -> pd.Series:
    if series.nunique(dropna=True) <= 1:
        return pd.Series(NEUTRAL_SCORE, index=series.index, dtype=float)
    ranked = series.rank(method="average", pct=True)
    score = ranked * 100
    if not higher_is_risk:
        score = (1 - ranked) * 100
    return score.clip(0, 100).fillna(NEUTRAL_SCORE)


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
    if score >= RISK_TIER_THRESHOLDS["critical_min"]:
        return "Critical"
    if score >= RISK_TIER_THRESHOLDS["high_min"]:
        return "High"
    if score >= RISK_TIER_THRESHOLDS["medium_min"]:
        return "Medium"
    return "Low"


def _recommended_action(row: pd.Series) -> str:
    driver_action_map = {
        "pricing_risk_score": "review pricing variance",
        "discount_dependency_score": "review discount terms",
        "margin_erosion_score": "review margin guardrails",
    }

    if row["risk_tier"] == "Low":
        return "monitor only"
    if row["risk_tier"] == "Medium":
        return "review segment pricing"

    return driver_action_map.get(row["main_risk_driver"], "review segment pricing")


def score_customer_pricing_risk(customer_profile: pd.DataFrame) -> pd.DataFrame:
    scored = customer_profile.copy()

    scored["score_reliability_weight"] = (scored["total_orders"] / MIN_RELIABLE_ORDER_COUNT).clip(
        lower=0, upper=1
    )
    scored["low_data_flag"] = (scored["total_orders"] < MIN_RELIABLE_ORDER_COUNT).astype(int)

    # Relative components detect peer-level outliers.
    rel_discount_depth = _percentile_score(scored["weighted_discount_pct"], higher_is_risk=True)
    rel_price_realization_residual = _percentile_score(
        scored["avg_abs_price_realization_residual_pct"], higher_is_risk=True
    )
    rel_discount_share = _percentile_score(
        scored["share_orders_high_discount"], higher_is_risk=True
    )
    rel_high_discount_revenue = _percentile_score(
        scored["revenue_high_discount_share"], higher_is_risk=True
    )
    rel_repeat_behavior = _percentile_score(scored["repeat_discount_behavior"], higher_is_risk=True)
    rel_margin_erosion = _percentile_score(scored["avg_margin_proxy_pct"], higher_is_risk=False)

    # Absolute components detect policy breaches regardless of peer distribution.
    abs_discount_depth = _scale_excess(
        scored["weighted_discount_pct"],
        WEIGHTED_DISCOUNT_POLICY_THRESHOLD,
        float(_SCALING_RANGES["weighted_discount_excess"]),
    )
    abs_price_realization_residual = _scale_excess(
        scored["avg_abs_price_realization_residual_pct"],
        PRICE_REALIZATION_RESIDUAL_ABS_MEAN_THRESHOLD,
        float(_SCALING_RANGES["price_realization_residual_excess"]),
    )
    abs_high_discount_order_share = _scale_excess(
        scored["share_orders_high_discount"],
        HIGH_DISCOUNT_ORDER_SHARE_THRESHOLD,
        float(_SCALING_RANGES["high_discount_order_share_excess"]),
    )
    abs_high_discount_revenue_share = _scale_excess(
        scored["revenue_high_discount_share"],
        HIGH_DISCOUNT_REVENUE_SHARE_THRESHOLD,
        float(_SCALING_RANGES["high_discount_revenue_share_excess"]),
    )
    abs_repeat_behavior = _scale_excess(
        scored["repeat_discount_behavior"],
        REPEAT_DISCOUNT_BEHAVIOR_THRESHOLD,
        float(_SCALING_RANGES["repeat_discount_behavior_excess"]),
    )
    abs_margin_shortfall = _scale_shortfall(
        scored["avg_margin_proxy_pct"],
        MARGIN_PROXY_FLOOR_THRESHOLD,
        float(_SCALING_RANGES["margin_proxy_shortfall"]),
    )

    raw_pricing_risk = _W_PRICING["rel_blend"] * (
        _W_PRICING["rel_discount_depth"] * rel_discount_depth
        + _W_PRICING["rel_price_residual"] * rel_price_realization_residual
        + _W_PRICING["rel_discount_share"] * rel_discount_share
    ) + _W_PRICING["abs_blend"] * (
        _W_PRICING["abs_discount_depth"] * abs_discount_depth
        + _W_PRICING["abs_price_residual"] * abs_price_realization_residual
        + _W_PRICING["abs_high_discount_order_share"] * abs_high_discount_order_share
    )
    raw_discount_dependency = _W_DEPENDENCY["rel_blend"] * (
        _W_DEPENDENCY["rel_high_discount_revenue"] * rel_high_discount_revenue
        + _W_DEPENDENCY["rel_repeat_behavior"] * rel_repeat_behavior
        + _W_DEPENDENCY["rel_discount_share"] * rel_discount_share
    ) + _W_DEPENDENCY["abs_blend"] * (
        _W_DEPENDENCY["abs_high_discount_revenue_share"] * abs_high_discount_revenue_share
        + _W_DEPENDENCY["abs_repeat_behavior"] * abs_repeat_behavior
        + _W_DEPENDENCY["abs_high_discount_order_share"] * abs_high_discount_order_share
    )
    raw_margin_erosion = _W_MARGIN["rel_blend"] * (
        _W_MARGIN["rel_margin_erosion"] * rel_margin_erosion
        + _W_MARGIN["rel_discount_depth"] * rel_discount_depth
        + _W_MARGIN["rel_high_discount_revenue"] * rel_high_discount_revenue
    ) + _W_MARGIN["abs_blend"] * (
        _W_MARGIN["abs_margin_shortfall"] * abs_margin_shortfall
        + _W_MARGIN["abs_discount_depth"] * abs_discount_depth
        + _W_MARGIN["abs_high_discount_revenue_share"] * abs_high_discount_revenue_share
    )

    scored["pricing_risk_score"] = _stabilize_with_reliability(
        raw_pricing_risk, scored["score_reliability_weight"]
    )
    scored["discount_dependency_score"] = _stabilize_with_reliability(
        raw_discount_dependency, scored["score_reliability_weight"]
    )
    scored["margin_erosion_score"] = _stabilize_with_reliability(
        raw_margin_erosion, scored["score_reliability_weight"]
    )
    scored["governance_priority_score"] = (
        PRIORITY_WEIGHTS["pricing_risk_score"] * scored["pricing_risk_score"]
        + PRIORITY_WEIGHTS["discount_dependency_score"] * scored["discount_dependency_score"]
        + PRIORITY_WEIGHTS["margin_erosion_score"] * scored["margin_erosion_score"]
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
        "weighted_discount_pct",
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

    return (
        scored[ordered_columns]
        .sort_values("governance_priority_score", ascending=False)
        .reset_index(drop=True)
    )


def build_risk_outputs(feature_tables: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
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
