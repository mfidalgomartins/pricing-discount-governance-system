from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

DASHBOARD_THRESHOLD_KEYS = {
    "weighted_discount_warn",
    "weighted_discount_critical",
    "margin_risk_share_warn",
    "margin_risk_share_critical",
    "high_risk_count_warn",
    "high_risk_count_critical",
}
POLICY_TOP_LEVEL_KEYS = {
    "pricing_health",
    "customer_risk_scoring",
    "discounted_threshold",
    "high_discount_threshold",
    "margin_at_risk_proxy_max",
    "high_discount_sensitivity_thresholds",
    "methodology_note",
}


def _require_exact_keys(payload: dict[str, Any], expected: set[str], name: str) -> None:
    missing = expected - payload.keys()
    unexpected = payload.keys() - expected
    if not missing and not unexpected:
        return

    details = []
    if missing:
        details.append(f"missing={sorted(missing)}")
    if unexpected:
        details.append(f"unexpected={sorted(unexpected)}")
    raise ValueError(f"Invalid {name} keys: " + ", ".join(details))


def _assert_weight_sum(weights: dict[str, Any], keys: list[str], group_name: str) -> None:
    total = sum(float(weights[key]) for key in keys)
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"{group_name} weights must sum to 1.0; found {total:.6f}")


@lru_cache(maxsize=1)
def load_policy_thresholds() -> dict[str, Any]:
    policy_path = Path(__file__).resolve().parents[2] / "config" / "policy_thresholds.json"
    if not policy_path.exists():
        raise FileNotFoundError(f"Policy threshold config not found: {policy_path}")
    payload = json.loads(policy_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Policy threshold config must contain a JSON object")
    policy: dict[str, Any] = payload
    _require_exact_keys(policy, POLICY_TOP_LEVEL_KEYS, "policy threshold")

    high_discount_threshold = float(policy["high_discount_threshold"])
    discounted_threshold = float(policy["discounted_threshold"])
    margin_at_risk_proxy_max = float(policy["margin_at_risk_proxy_max"])
    sensitivity_thresholds = [
        float(value) for value in policy["high_discount_sensitivity_thresholds"]
    ]
    if not 0 <= high_discount_threshold <= 1:
        raise ValueError("high_discount_threshold must be within [0, 1]")
    if not 0 <= discounted_threshold < high_discount_threshold:
        raise ValueError("discounted_threshold must be within [0, high_discount_threshold)")
    if not 0 <= margin_at_risk_proxy_max <= 1:
        raise ValueError("margin_at_risk_proxy_max must be within [0, 1]")
    if not sensitivity_thresholds or any(
        value < 0 or value > 1 for value in sensitivity_thresholds
    ):
        raise ValueError("high_discount_sensitivity_thresholds must contain values within [0, 1]")
    if high_discount_threshold not in sensitivity_thresholds:
        raise ValueError(
            "high_discount_threshold must be included in high_discount_sensitivity_thresholds"
        )
    if sensitivity_thresholds != sorted(set(sensitivity_thresholds)):
        raise ValueError("high_discount_sensitivity_thresholds must be sorted and unique")

    scoring = policy["customer_risk_scoring"]
    if not isinstance(scoring, dict):
        raise ValueError("customer_risk_scoring must contain a JSON object")
    bounded_scoring_values = {
        "weighted_discount_policy_threshold": scoring["weighted_discount_policy_threshold"],
        "high_discount_order_share_threshold": scoring["high_discount_order_share_threshold"],
        "high_discount_revenue_share_threshold": scoring["high_discount_revenue_share_threshold"],
        "repeat_discount_behavior_threshold": scoring["repeat_discount_behavior_threshold"],
        "margin_proxy_floor_threshold": scoring["margin_proxy_floor_threshold"],
        "price_realization_residual_abs_mean_threshold": scoring[
            "price_realization_residual_abs_mean_threshold"
        ],
    }
    invalid_scoring_values = [
        name for name, value in bounded_scoring_values.items() if not 0 <= float(value) <= 1
    ]
    if invalid_scoring_values:
        raise ValueError(
            "Customer risk thresholds must be within [0, 1]: " + ", ".join(invalid_scoring_values)
        )

    scaling_ranges = scoring["scaling_ranges"]
    invalid_scaling_ranges = [name for name, value in scaling_ranges.items() if float(value) <= 0]
    if invalid_scaling_ranges:
        raise ValueError(
            "Customer risk scaling ranges must be positive: " + ", ".join(invalid_scaling_ranges)
        )

    min_reliable_order_count = scoring["min_reliable_order_count"]
    if (
        isinstance(min_reliable_order_count, bool)
        or not isinstance(min_reliable_order_count, int)
        or min_reliable_order_count <= 0
    ):
        raise ValueError("min_reliable_order_count must be a positive integer")

    neutral_score = scoring["neutral_score"]
    if (
        isinstance(neutral_score, bool)
        or not isinstance(neutral_score, (int, float))
        or not 0 <= float(neutral_score) <= 100
    ):
        raise ValueError("neutral_score must be numeric and within [0, 100]")

    weights = scoring["weights"]
    _assert_weight_sum(
        weights["governance_priority"],
        ["pricing_risk_score", "discount_dependency_score", "margin_erosion_score"],
        "governance_priority",
    )
    for score_name in ["pricing_risk", "discount_dependency", "margin_erosion"]:
        score_weights = weights[score_name]
        _assert_weight_sum(score_weights, ["rel_blend", "abs_blend"], f"{score_name} blend")
        _assert_weight_sum(
            score_weights,
            [key for key in score_weights if key.startswith("rel_") and key != "rel_blend"],
            f"{score_name} relative",
        )
        _assert_weight_sum(
            score_weights,
            [key for key in score_weights if key.startswith("abs_") and key != "abs_blend"],
            f"{score_name} absolute",
        )

    tiers = scoring["risk_tiers"]
    if not 100 >= tiers["critical_min"] > tiers["high_min"] > tiers["medium_min"] >= 0:
        raise ValueError("Risk tier thresholds must be strictly descending within [0, 100]")

    health = policy["pricing_health"]
    if health["healthy_weighted_discount_max"] > health["mixed_weighted_discount_max"]:
        raise ValueError("Healthy weighted-discount threshold cannot exceed mixed threshold")
    if (
        health["healthy_high_discount_revenue_share_max"]
        > health["mixed_high_discount_revenue_share_max"]
    ):
        raise ValueError("Healthy high-discount share threshold cannot exceed mixed threshold")
    if health["healthy_margin_proxy_min"] < health["mixed_margin_proxy_min"]:
        raise ValueError("Healthy margin threshold cannot be below mixed threshold")

    return policy


def get_high_discount_threshold() -> float:
    return float(load_policy_thresholds()["high_discount_threshold"])


def get_discounted_threshold() -> float:
    return float(load_policy_thresholds()["discounted_threshold"])


def get_margin_at_risk_proxy_max() -> float:
    return float(load_policy_thresholds()["margin_at_risk_proxy_max"])


def _validate_dashboard_policy(policy: dict[str, Any]) -> None:
    _require_exact_keys(policy, {"thresholds"}, "dashboard policy")
    thresholds = policy.get("thresholds")
    if not isinstance(thresholds, dict):
        raise ValueError("Dashboard policy must define a thresholds object")

    _require_exact_keys(thresholds, DASHBOARD_THRESHOLD_KEYS, "dashboard threshold")

    ratio_keys = {
        "weighted_discount_warn",
        "weighted_discount_critical",
        "margin_risk_share_warn",
        "margin_risk_share_critical",
    }
    invalid_ratios = [
        key
        for key in ratio_keys
        if isinstance(thresholds[key], bool)
        or not isinstance(thresholds[key], (int, float))
        or not 0 <= float(thresholds[key]) <= 1
    ]
    if invalid_ratios:
        raise ValueError(
            "Dashboard ratio thresholds must be numeric values within [0, 1]: "
            + ", ".join(sorted(invalid_ratios))
        )

    count_keys = {"high_risk_count_warn", "high_risk_count_critical"}
    invalid_counts = [
        key
        for key in count_keys
        if isinstance(thresholds[key], bool)
        or not isinstance(thresholds[key], int)
        or thresholds[key] < 0
    ]
    if invalid_counts:
        raise ValueError(
            "Dashboard count thresholds must be non-negative integers: "
            + ", ".join(sorted(invalid_counts))
        )

    if thresholds["weighted_discount_warn"] >= thresholds["weighted_discount_critical"]:
        raise ValueError("Dashboard weighted-discount warning must be below critical")
    if thresholds["margin_risk_share_warn"] >= thresholds["margin_risk_share_critical"]:
        raise ValueError("Dashboard margin-risk warning must be below critical")
    if thresholds["high_risk_count_warn"] >= thresholds["high_risk_count_critical"]:
        raise ValueError("Dashboard high-risk count warning must be below critical")


@lru_cache(maxsize=1)
def load_dashboard_policy() -> dict[str, Any]:
    policy_path = Path(__file__).resolve().parents[2] / "config" / "dashboard_policy.json"
    if not policy_path.exists():
        raise FileNotFoundError(f"Dashboard policy config not found: {policy_path}")

    payload = json.loads(policy_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("Dashboard policy must contain a JSON object")
    policy: dict[str, Any] = payload
    _validate_dashboard_policy(policy)
    return policy
