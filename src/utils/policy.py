from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any


def _assert_weight_sum(weights: dict[str, Any], keys: list[str], group_name: str) -> None:
    total = sum(float(weights[key]) for key in keys)
    if abs(total - 1.0) > 1e-9:
        raise ValueError(f"{group_name} weights must sum to 1.0; found {total:.6f}")


@lru_cache(maxsize=1)
def load_policy_thresholds() -> dict[str, Any]:
    policy_path = Path(__file__).resolve().parents[2] / "config" / "policy_thresholds.json"
    if not policy_path.exists():
        raise FileNotFoundError(f"Policy threshold config not found: {policy_path}")
    policy = json.loads(policy_path.read_text(encoding="utf-8"))

    high_discount_threshold = float(policy["high_discount_threshold"])
    sensitivity_thresholds = [float(value) for value in policy["high_discount_sensitivity_thresholds"]]
    if not 0 <= high_discount_threshold <= 1:
        raise ValueError("high_discount_threshold must be within [0, 1]")
    if not sensitivity_thresholds or any(value < 0 or value > 1 for value in sensitivity_thresholds):
        raise ValueError("high_discount_sensitivity_thresholds must contain values within [0, 1]")
    if high_discount_threshold not in sensitivity_thresholds:
        raise ValueError("high_discount_threshold must be included in high_discount_sensitivity_thresholds")
    if sensitivity_thresholds != sorted(set(sensitivity_thresholds)):
        raise ValueError("high_discount_sensitivity_thresholds must be sorted and unique")

    scoring = policy["customer_risk_scoring"]
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
    if health["healthy_high_discount_revenue_share_max"] > health["mixed_high_discount_revenue_share_max"]:
        raise ValueError("Healthy high-discount share threshold cannot exceed mixed threshold")
    if health["healthy_margin_proxy_min"] < health["mixed_margin_proxy_min"]:
        raise ValueError("Healthy margin threshold cannot be below mixed threshold")

    return policy


def get_high_discount_threshold() -> float:
    return float(load_policy_thresholds()["high_discount_threshold"])
