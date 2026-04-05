from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd


HEALTHY_WEIGHTED_DISCOUNT_MAX = 0.12
HEALTHY_HIGH_DISCOUNT_REVENUE_SHARE_MAX = 0.20
HEALTHY_MARGIN_PROXY_MIN = 0.45

MIXED_WEIGHTED_DISCOUNT_MAX = 0.18
MIXED_HIGH_DISCOUNT_REVENUE_SHARE_MAX = 0.30
MIXED_MARGIN_PROXY_MIN = 0.40


def _pct_rank(series: pd.Series, reverse: bool = False) -> pd.Series:
    ranked = series.rank(pct=True)
    return (1 - ranked) if reverse else ranked


def _compute_growth_2025_vs_2023(yearly: pd.DataFrame) -> float | None:
    if {2023, 2025}.issubset(set(yearly["year"])):
        rev_2023 = yearly.loc[yearly["year"] == 2023, "revenue"].iloc[0]
        rev_2025 = yearly.loc[yearly["year"] == 2025, "revenue"].iloc[0]
        return (rev_2025 / rev_2023 - 1) * 100 if rev_2023 else np.nan
    return None


def _pricing_health_verdict(overall: pd.Series) -> tuple[str, str]:
    weighted_discount = float(overall["weighted_realized_discount"])
    high_discount_share = float(overall["high_discount_revenue_share"])
    margin_proxy = float(overall["margin_proxy_pct"])

    if (
        weighted_discount <= HEALTHY_WEIGHTED_DISCOUNT_MAX
        and high_discount_share <= HEALTHY_HIGH_DISCOUNT_REVENUE_SHARE_MAX
        and margin_proxy >= HEALTHY_MARGIN_PROXY_MIN
    ):
        return (
            "Healthy pricing discipline",
            "Discount intensity is controlled and margin quality remains robust.",
        )

    if (
        weighted_discount <= MIXED_WEIGHTED_DISCOUNT_MAX
        and high_discount_share <= MIXED_HIGH_DISCOUNT_REVENUE_SHARE_MAX
        and margin_proxy >= MIXED_MARGIN_PROXY_MIN
    ):
        return (
            "Mixed pricing quality",
            "Growth quality is acceptable but discount dependency requires active monitoring.",
        )

    return (
        "Discount-reliant growth risk",
        "Growth is materially supported by high discounting and exposes margin quality.",
    )


def _build_threshold_sensitivity(pricing: pd.DataFrame) -> pd.DataFrame:
    thresholds = [0.15, 0.20, 0.25]
    rows: list[dict] = []

    customer_revenue = pricing.groupby("customer_id", as_index=False).agg(total_revenue=("line_revenue", "sum"))

    for threshold in thresholds:
        high_discount_mask = pricing["discount_depth"] >= threshold
        high_discount_revenue = float(pricing.loc[high_discount_mask, "line_revenue"].sum())
        total_revenue = float(pricing["line_revenue"].sum())

        customer_high_discount = (
            pricing.loc[high_discount_mask]
            .groupby("customer_id", as_index=False)
            .agg(high_discount_revenue=("line_revenue", "sum"))
        )
        customer_sensitivity = customer_revenue.merge(customer_high_discount, on="customer_id", how="left").fillna(
            {"high_discount_revenue": 0.0}
        )
        customer_sensitivity["high_discount_share"] = np.where(
            customer_sensitivity["total_revenue"] > 0,
            customer_sensitivity["high_discount_revenue"] / customer_sensitivity["total_revenue"],
            0.0,
        )

        rows.append(
            {
                "high_discount_threshold": threshold,
                "high_discount_revenue_share": (
                    high_discount_revenue / total_revenue if total_revenue > 0 else np.nan
                ),
                "high_discount_order_item_share": float(high_discount_mask.mean()),
                "margin_proxy_pct_on_high_discount": float(
                    pricing.loc[high_discount_mask, "margin_proxy_pct"].mean()
                )
                if high_discount_mask.any()
                else np.nan,
                "customer_share_over_40pct_high_discount_revenue": float(
                    (customer_sensitivity["high_discount_share"] >= 0.40).mean()
                ),
                "revenue_with_margin_at_risk": float(
                    pricing.loc[high_discount_mask & (pricing["margin_proxy_pct"] < 0.35), "line_revenue"].sum()
                ),
            }
        )

    return pd.DataFrame(rows)


def _build_governance_action_queue(
    pricing: pd.DataFrame,
    customer_risk_scores: pd.DataFrame | None,
) -> pd.DataFrame:
    if customer_risk_scores is None or customer_risk_scores.empty:
        return pd.DataFrame()

    customer_leakage = (
        pricing.groupby("customer_id", as_index=False)
        .agg(
            revenue_in_scope=("line_revenue", "sum"),
            total_list_revenue=("line_list_revenue", "sum"),
            high_discount_revenue=("line_revenue", lambda s: s[pricing.loc[s.index, "discount_depth"] >= 0.20].sum()),
            margin_at_risk_revenue=(
                "line_revenue",
                lambda s: s[
                    (pricing.loc[s.index, "discount_depth"] >= 0.20)
                    & (pricing.loc[s.index, "margin_proxy_pct"] < 0.35)
                ].sum(),
            ),
            discount_leakage_value=("line_revenue", lambda s: (pricing.loc[s.index, "line_list_revenue"] - s).sum()),
        )
    )

    queue = customer_risk_scores.merge(customer_leakage, on="customer_id", how="left")
    queue["high_discount_revenue"] = queue["high_discount_revenue"].fillna(0.0)
    queue["margin_at_risk_revenue"] = queue["margin_at_risk_revenue"].fillna(0.0)
    queue["discount_leakage_value"] = queue["discount_leakage_value"].fillna(0.0)
    queue["revenue_in_scope"] = queue["revenue_in_scope"].fillna(queue["total_revenue"])
    queue["priority_value_proxy"] = (
        queue["governance_priority_score"] / 100 * queue["margin_at_risk_revenue"]
    )

    keep_cols = [
        "customer_id",
        "segment",
        "region",
        "risk_tier",
        "main_risk_driver",
        "recommended_action",
        "governance_priority_score",
        "total_revenue",
        "revenue_in_scope",
        "high_discount_revenue",
        "margin_at_risk_revenue",
        "discount_leakage_value",
        "priority_value_proxy",
    ]
    return queue[keep_cols].sort_values(
        ["priority_value_proxy", "governance_priority_score", "margin_at_risk_revenue"],
        ascending=False,
    )


def _overall_pricing_health(pricing: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    total_revenue = float(pricing["line_revenue"].sum())
    total_list_revenue = float(pricing["line_list_revenue"].sum())
    total_margin = float(pricing["gross_margin_value"].sum())

    high_discount_revenue = float(pricing.loc[pricing["discount_depth"] >= 0.20, "line_revenue"].sum())
    avg_realized_discount = float(pricing["discount_depth"].mean())
    weighted_discount = 1 - (total_revenue / total_list_revenue) if total_list_revenue else np.nan
    price_realization = total_revenue / total_list_revenue if total_list_revenue else np.nan

    overall = pd.DataFrame(
        [
            {
                "total_revenue": total_revenue,
                "total_list_revenue": total_list_revenue,
                "total_margin_proxy_value": total_margin,
                "avg_realized_discount": avg_realized_discount,
                "weighted_realized_discount": weighted_discount,
                "high_discount_revenue_share": high_discount_revenue / total_revenue if total_revenue else np.nan,
                "price_realization": price_realization,
                "margin_proxy_pct": total_margin / total_revenue if total_revenue else np.nan,
            }
        ]
    )

    yearly = (
        pricing.groupby("year", as_index=False)
        .agg(
            revenue=("line_revenue", "sum"),
            list_revenue=("line_list_revenue", "sum"),
            margin_proxy_value=("gross_margin_value", "sum"),
            avg_realized_discount=("discount_depth", "mean"),
            high_discount_revenue=("line_revenue", lambda s: s[pricing.loc[s.index, "discount_depth"] >= 0.20].sum()),
        )
        .sort_values("year")
    )
    yearly["price_realization"] = np.where(yearly["list_revenue"] > 0, yearly["revenue"] / yearly["list_revenue"], np.nan)
    yearly["weighted_discount"] = 1 - yearly["price_realization"]
    yearly["margin_proxy_pct"] = np.where(yearly["revenue"] > 0, yearly["margin_proxy_value"] / yearly["revenue"], np.nan)
    yearly["high_discount_revenue_share"] = np.where(
        yearly["revenue"] > 0,
        yearly["high_discount_revenue"] / yearly["revenue"],
        np.nan,
    )

    return overall, yearly


def _discount_dependency(pricing: pd.DataFrame, customer_profile: pd.DataFrame) -> dict[str, pd.DataFrame]:
    customer_dependency = customer_profile.copy()
    customer_dependency["high_discount_revenue_value"] = (
        customer_dependency["revenue_high_discount_share"] * customer_dependency["total_revenue"]
    )
    customer_dependency = customer_dependency.sort_values(
        ["revenue_high_discount_share", "total_revenue"], ascending=[False, False]
    )

    segment_dependency = (
        pricing.groupby("segment", as_index=False)
        .agg(
            revenue=("line_revenue", "sum"),
            avg_discount_pct=("discount_depth", "mean"),
            avg_margin_proxy_pct=("margin_proxy_pct", "mean"),
            high_discount_revenue=("line_revenue", lambda s: s[pricing.loc[s.index, "discount_depth"] >= 0.20].sum()),
            repeat_discount_behavior=("discounted_flag", "mean"),
        )
        .sort_values("high_discount_revenue", ascending=False)
    )
    segment_dependency["high_discount_revenue_share"] = np.where(
        segment_dependency["revenue"] > 0,
        segment_dependency["high_discount_revenue"] / segment_dependency["revenue"],
        np.nan,
    )

    product_dependency = (
        pricing.groupby(["product_id", "product_name", "category"], as_index=False)
        .agg(
            revenue=("line_revenue", "sum"),
            avg_discount_pct=("discount_depth", "mean"),
            high_discount_revenue=("line_revenue", lambda s: s[pricing.loc[s.index, "discount_depth"] >= 0.20].sum()),
            order_lines=("order_item_id", "count"),
        )
        .sort_values("revenue", ascending=False)
    )
    product_dependency["high_discount_revenue_share"] = np.where(
        product_dependency["revenue"] > 0,
        product_dependency["high_discount_revenue"] / product_dependency["revenue"],
        np.nan,
    )

    top_n = max(1, int(np.ceil(len(customer_dependency) * 0.10)))
    high_dependency_revenue_share = (
        customer_dependency.head(top_n)["total_revenue"].sum() / customer_dependency["total_revenue"].sum()
        if customer_dependency["total_revenue"].sum() > 0
        else np.nan
    )

    concentration = pd.DataFrame(
        [
            {
                "top_decile_customers": top_n,
                "revenue_share_of_top_dependency_decile": high_dependency_revenue_share,
                "avg_repeat_discount_behavior": float(customer_dependency["repeat_discount_behavior"].mean()),
                "avg_share_orders_discounted": float(customer_dependency["share_orders_discounted"].mean()),
            }
        ]
    )

    return {
        "customer_discount_dependency": customer_dependency,
        "segment_discount_dependency": segment_dependency,
        "product_discount_dependency": product_dependency,
        "discount_dependency_concentration": concentration,
    }


def _margin_erosion_risk(pricing: pd.DataFrame) -> pd.DataFrame:
    segment_category = (
        pricing.groupby(["segment", "category"], as_index=False)
        .agg(
            revenue=("line_revenue", "sum"),
            list_revenue=("line_list_revenue", "sum"),
            gross_margin_value=("gross_margin_value", "sum"),
            avg_discount_pct=("discount_depth", "mean"),
            high_discount_share=("high_discount_flag", "mean"),
            order_lines=("order_item_id", "count"),
        )
        .sort_values("revenue", ascending=False)
    )

    segment_category["margin_proxy_pct"] = np.where(
        segment_category["revenue"] > 0,
        segment_category["gross_margin_value"] / segment_category["revenue"],
        np.nan,
    )
    segment_category["discount_leakage_value"] = segment_category["list_revenue"] - segment_category["revenue"]
    segment_category["margin_erosion_risk_score"] = (
        100
        * (
            0.45 * _pct_rank(segment_category["avg_discount_pct"])
            + 0.30 * _pct_rank(segment_category["high_discount_share"])
            + 0.25 * _pct_rank(segment_category["margin_proxy_pct"], reverse=True)
        )
    )

    return segment_category.sort_values("margin_erosion_risk_score", ascending=False)


def _pricing_inconsistency(pricing: pd.DataFrame) -> dict[str, pd.DataFrame]:
    rep_behavior = (
        pricing.groupby(["sales_rep_id", "team", "rep_region"], as_index=False)
        .agg(
            revenue=("line_revenue", "sum"),
            order_lines=("order_item_id", "count"),
            avg_discount_pct=("discount_depth", "mean"),
            discount_std=("discount_depth", "std"),
            avg_margin_proxy_pct=("margin_proxy_pct", "mean"),
        )
        .query("order_lines >= 120")
    )

    rep_behavior["peer_avg_discount"] = rep_behavior.groupby(["team", "rep_region"])["avg_discount_pct"].transform("mean")
    rep_behavior["peer_discount_std"] = rep_behavior.groupby(["team", "rep_region"])["avg_discount_pct"].transform("std")
    rep_behavior["peer_discount_std"] = rep_behavior["peer_discount_std"].replace(0, np.nan)
    rep_behavior["discount_zscore_vs_peers"] = (
        (rep_behavior["avg_discount_pct"] - rep_behavior["peer_avg_discount"]) / rep_behavior["peer_discount_std"]
    ).fillna(0)
    rep_behavior["discount_outlier_flag"] = rep_behavior["discount_zscore_vs_peers"].abs() >= 2

    channel_region = (
        pricing.groupby(["sales_channel", "region"], as_index=False)
        .agg(
            revenue=("line_revenue", "sum"),
            avg_discount_pct=("discount_depth", "mean"),
            avg_margin_proxy_pct=("margin_proxy_pct", "mean"),
            order_lines=("order_item_id", "count"),
        )
        .sort_values("avg_discount_pct", ascending=False)
    )

    product_variance = (
        pricing.groupby(["product_id", "product_name", "category", "sales_channel"], as_index=False)
        .agg(
            revenue=("line_revenue", "sum"),
            order_lines=("order_item_id", "count"),
            avg_discount_pct=("discount_depth", "mean"),
            realized_price_mean=("realized_price", "mean"),
            realized_price_std=("realized_price", "std"),
        )
        .query("order_lines >= 25")
    )
    product_variance["realized_price_cv"] = np.where(
        product_variance["realized_price_mean"] > 0,
        product_variance["realized_price_std"] / product_variance["realized_price_mean"],
        np.nan,
    )
    product_variance = product_variance.sort_values("realized_price_cv", ascending=False)

    return {
        "rep_pricing_inconsistency": rep_behavior.sort_values("discount_zscore_vs_peers", ascending=False),
        "channel_region_pricing_inconsistency": channel_region,
        "product_price_variance": product_variance,
    }


def _product_level_patterns(pricing: pd.DataFrame) -> pd.DataFrame:
    product_view = (
        pricing.groupby(["product_id", "product_name", "category"], as_index=False)
        .agg(
            revenue=("line_revenue", "sum"),
            list_revenue=("line_list_revenue", "sum"),
            order_lines=("order_item_id", "count"),
            avg_discount_pct=("discount_depth", "mean"),
            high_discount_share=("high_discount_flag", "mean"),
            avg_margin_proxy_pct=("margin_proxy_pct", "mean"),
        )
        .sort_values("revenue", ascending=False)
    )

    product_view["price_realization"] = np.where(
        product_view["list_revenue"] > 0,
        product_view["revenue"] / product_view["list_revenue"],
        np.nan,
    )

    conditions = [
        (product_view["avg_discount_pct"] < 0.15)
        & (product_view["high_discount_share"] < 0.25)
        & (product_view["avg_margin_proxy_pct"] > 0.40),
        (product_view["high_discount_share"] >= 0.75) | (product_view["avg_discount_pct"] >= 0.35),
        (product_view["avg_margin_proxy_pct"] < 0.30) & (product_view["avg_discount_pct"] >= 0.25),
    ]
    choices = ["Sold cleanly", "Discount-reliant", "Margin-pressure"]
    product_view["pricing_pattern"] = np.select(conditions, choices, default="Mixed")

    product_view["governance_concern_score"] = (
        100
        * (
            0.40 * _pct_rank(product_view["avg_discount_pct"])
            + 0.35 * _pct_rank(product_view["high_discount_share"])
            + 0.25 * _pct_rank(product_view["avg_margin_proxy_pct"], reverse=True)
        )
    )

    return product_view.sort_values("governance_concern_score", ascending=False)


def _validation_checks(
    pricing: pd.DataFrame,
    processed_tables: Dict[str, pd.DataFrame],
    yearly_health: pd.DataFrame,
    segment_dependency: pd.DataFrame,
    overall_health: pd.DataFrame,
    customer_profile: pd.DataFrame,
) -> pd.DataFrame:
    checks: list[dict] = []

    def add_check(name: str, condition: bool, detail: str) -> None:
        checks.append(
            {
                "check_name": name,
                "status": "PASS" if condition else "FAIL",
                "detail": detail,
            }
        )

    add_check(
        "row_count_sanity",
        len(pricing) == len(processed_tables["order_item_enriched"]),
        f"pricing rows={len(pricing)}, enriched rows={len(processed_tables['order_item_enriched'])}",
    )

    key_columns = ["order_item_id", "order_id", "customer_id", "product_id", "line_revenue", "discount_depth"]
    key_nulls = int(pricing[key_columns].isna().sum().sum())
    add_check("null_sanity_core_columns", key_nulls == 0, f"null count in key columns={key_nulls}")

    total_revenue = float(pricing["line_revenue"].sum())
    total_list_revenue = float(pricing["line_list_revenue"].sum())
    add_check(
        "magnitude_checks_positive_revenue",
        total_revenue > 0 and total_list_revenue >= total_revenue,
        f"total_revenue={total_revenue:.2f}, total_list_revenue={total_list_revenue:.2f}",
    )

    month_series = pd.period_range(pricing["order_date"].min(), pricing["order_date"].max(), freq="M")
    observed_months = pd.PeriodIndex(pricing["order_date"], freq="M").unique()
    continuity_ok = len(month_series.difference(observed_months)) == 0
    add_check("trend_continuity_monthly", continuity_ok, f"expected_months={len(month_series)}, observed_months={len(observed_months)}")

    expected_years = sorted(pricing["order_date"].dt.year.unique().tolist())
    observed_years = sorted(yearly_health["year"].tolist())
    add_check(
        "time_window_year_coverage",
        expected_years == observed_years,
        f"expected_years={expected_years}, observed_years={observed_years}",
    )

    segment_total = float(segment_dependency["revenue"].sum())
    subtotal_ok = abs(segment_total - total_revenue) <= max(1.0, total_revenue * 0.0001)
    add_check("subtotal_total_consistency", subtotal_ok, f"segment_total={segment_total:.2f}, total={total_revenue:.2f}")

    share_columns = ["high_discount_revenue_share"]
    share_ok = True
    for col in share_columns:
        if col in yearly_health.columns:
            share_ok &= bool(((yearly_health[col] >= -1e-9) & (yearly_health[col] <= 1 + 1e-9)).all())
    share_ok &= bool(
        0 - 1e-9 <= overall_health["high_discount_revenue_share"].iloc[0] <= 1 + 1e-9
    )
    add_check("denominator_correctness_shares", share_ok, "share metrics constrained to [0,1]")

    weighted_discount_direct = float(np.average(pricing["discount_depth"], weights=pricing["line_list_revenue"]))
    weighted_discount_from_ratio = float(1 - (total_revenue / total_list_revenue)) if total_list_revenue else np.nan
    aggregation_ok = abs(weighted_discount_direct - weighted_discount_from_ratio) <= 0.001
    add_check(
        "aggregation_logic_weighted_discount",
        aggregation_ok,
        f"weighted_direct={weighted_discount_direct:.6f}, weighted_ratio={weighted_discount_from_ratio:.6f}",
    )

    weighted_margin_direct = float(np.average(pricing["margin_proxy_pct"], weights=pricing["line_revenue"]))
    weighted_margin_from_totals = float(overall_health["margin_proxy_pct"].iloc[0])
    margin_aggregation_ok = abs(weighted_margin_direct - weighted_margin_from_totals) <= 0.001
    add_check(
        "aggregation_logic_weighted_margin",
        margin_aggregation_ok,
        f"weighted_direct={weighted_margin_direct:.6f}, weighted_totals={weighted_margin_from_totals:.6f}",
    )

    transacting_customers = int(pricing["customer_id"].nunique())
    scored_customers = int(customer_profile["customer_id"].nunique())
    coverage_ok = transacting_customers == scored_customers
    add_check(
        "population_coverage_transacting_customers",
        coverage_ok,
        f"transacting_customers={transacting_customers}, scored_customers={scored_customers}",
    )

    return pd.DataFrame(checks)


def _render_formal_report(payload: dict) -> str:
    overall = payload["overall_health"].iloc[0]
    yearly = payload["yearly_health"]
    segment_dependency = payload["segment_dependency"]
    margin_risk = payload["margin_erosion_risk"]
    rep_inconsistency = payload["rep_pricing_inconsistency"]
    product_patterns = payload["product_patterns"]
    threshold_sensitivity = payload["threshold_sensitivity"]
    action_queue = payload["governance_action_queue"]
    validations = payload["validation_checks"]
    analysis_window = payload["analysis_window"]
    verdict = payload["pricing_health_verdict"]
    verdict_reason = payload["pricing_health_reason"]

    growth_2025_vs_2023 = _compute_growth_2025_vs_2023(yearly)
    growth_line = (
        f"Revenue growth (2025 vs 2023): {growth_2025_vs_2023:.2f}%."
        if growth_2025_vs_2023 is not None and not np.isnan(growth_2025_vs_2023)
        else "Revenue growth (2025 vs 2023): N/A for current date window."
    )

    top_segment_dependency = segment_dependency.sort_values("high_discount_revenue_share", ascending=False).iloc[0]
    top_margin_risk = margin_risk.iloc[0]
    outlier_reps = int(rep_inconsistency["discount_outlier_flag"].sum()) if "discount_outlier_flag" in rep_inconsistency.columns else 0
    discount_reliant_products = int((product_patterns["pricing_pattern"] == "Discount-reliant").sum())

    recommendation_lines: list[str] = []
    if overall["high_discount_revenue_share"] >= 0.30:
        recommendation_lines.append("tighten approval thresholds for deals above 20% discount in exposed segment/channel combinations")
    if float(top_segment_dependency["high_discount_revenue_share"]) >= 0.40:
        recommendation_lines.append(
            f"review segment pricing architecture for {top_segment_dependency['segment']} where high-discount dependency is structurally elevated"
        )
    if outlier_reps > 0:
        recommendation_lines.append("investigate rep-level outliers and align incentives to price realization governance")
    else:
        recommendation_lines.append("maintain monthly rep-monitoring; no rep outlier currently breaches the z-score threshold")
    if discount_reliant_products > 0:
        recommendation_lines.append("redesign policy guardrails for discount-reliant products with weak pricing quality")
    else:
        recommendation_lines.append("monitor mixed-pattern products and tighten governance if a discount-reliant cohort emerges")
    if not action_queue.empty:
        recommendation_lines.append("activate a prioritized intervention queue using margin-at-risk and governance priority score")
    recommendation_lines.append("track weighted discount, high-discount revenue share, and margin proxy as recurring governance KPIs")

    sensitivity_lines = [
        (
            f"- Threshold >= {row.high_discount_threshold:.0%}: "
            f"high-discount revenue share {row.high_discount_revenue_share:.2%}, "
            f"customer exposure >=40% revenue {row.customer_share_over_40pct_high_discount_revenue:.2%}, "
            f"margin-at-risk revenue {row.revenue_with_margin_at_risk:,.2f}"
        )
        for row in threshold_sensitivity.itertuples(index=False)
    ]

    queue_lines: list[str] = []
    queue_preview = action_queue.head(5)
    if not queue_preview.empty:
        for row in queue_preview.itertuples(index=False):
            queue_lines.append(
                f"- {row.customer_id} ({row.segment}, {row.region}) -> {row.recommended_action}; "
                f"priority proxy={row.priority_value_proxy:,.2f}, margin-at-risk={row.margin_at_risk_revenue:,.2f}"
            )
    else:
        queue_lines.append("- Action queue unavailable (customer_risk_scores not provided in current run).")

    lines = [
        "# Formal Pricing Discipline Analysis Report",
        "",
        "## Executive Summary",
        f"Pricing discipline verdict: {verdict}.",
        verdict_reason,
        growth_line,
        f"Weighted realized discount: {overall['weighted_realized_discount']:.2%}; price realization: {overall['price_realization']:.2%}; high-discount revenue share: {overall['high_discount_revenue_share']:.2%}.",
        f"Most exposed segment (discount dependency): {top_segment_dependency['segment']} ({top_segment_dependency['high_discount_revenue_share']:.2%} high-discount revenue share).",
        f"Most exposed segment-category margin erosion pattern: {top_margin_risk['segment']} / {top_margin_risk['category']} (risk score={top_margin_risk['margin_erosion_risk_score']:.1f}).",
        f"Rep pricing inconsistency: {outlier_reps} reps flagged as peer outliers (|z|>=2).",
        "",
        "## Methodology",
        "- Analysis type: full business diagnostics with validation checks.",
        "- Tables used: order_item_pricing_metrics, customer_pricing_profile, customer_risk_scores, segment_pricing_summary, segment_channel_diagnostics.",
        f"- Time period: full available coverage ({analysis_window['coverage_start']} to {analysis_window['coverage_end']}).",
        "- Metric logic: realized discount, price realization, high-discount revenue share, margin proxy, repeat discount behavior, variance diagnostics.",
        "- Scoring interpretation: customer risk scoring blends peer-relative ranks with absolute policy-threshold breaches.",
        "",
        "## Detailed Findings",
        "### A. Overall Pricing Health",
        f"- Average realized discount: {overall['avg_realized_discount']:.2%}.",
        f"- Share of revenue under high discount (>=20%): {overall['high_discount_revenue_share']:.2%}.",
        f"- List vs realized performance (price realization): {overall['price_realization']:.2%}.",
        f"- Margin proxy: {overall['margin_proxy_pct']:.2%}.",
        "",
        "### B. Discount Dependency",
        f"- Segment with highest discount dependency: {top_segment_dependency['segment']} ({top_segment_dependency['high_discount_revenue_share']:.2%}).",
        f"- Customer top-decile revenue concentration (by dependency): {payload['dependency_concentration'].iloc[0]['revenue_share_of_top_dependency_decile']:.2%}.",
        f"- Average repeat discount behavior: {payload['dependency_concentration'].iloc[0]['avg_repeat_discount_behavior']:.2%}.",
        "",
        "### C. Margin Erosion Risk",
        f"- Highest risk segment/category: {top_margin_risk['segment']} / {top_margin_risk['category']}.",
        f"- Discount leakage value at that intersection: {top_margin_risk['discount_leakage_value']:.2f}.",
        "",
        "### D. Pricing Inconsistency",
        (
            f"- Rep outliers suggest inconsistent pricing governance across teams/regions (outliers={outlier_reps})."
            if outlier_reps > 0
            else "- No rep-level peer outliers are flagged at |z|>=2; inconsistency signal is concentrated more by channel/region than by individual rep."
        ),
        f"- Highest channel-region discount level: {payload['channel_region_inconsistency'].iloc[0]['sales_channel']} / {payload['channel_region_inconsistency'].iloc[0]['region']} ({payload['channel_region_inconsistency'].iloc[0]['avg_discount_pct']:.2%}).",
        "",
        "### E. Product-Level Patterns",
        f"- Products classified as discount-reliant: {discount_reliant_products} of {len(product_patterns)}.",
        f"- Products sold cleanly: {(product_patterns['pricing_pattern'] == 'Sold cleanly').sum()} of {len(product_patterns)}.",
        f"- Highest governance concern product: {product_patterns.iloc[0]['product_name']} (score={product_patterns.iloc[0]['governance_concern_score']:.1f}).",
        "",
        "### F. Threshold Sensitivity and Decision Impact",
        "How governance exposure changes when the high-discount threshold moves:",
    ]
    lines.extend(sensitivity_lines)
    lines.extend(
        [
            "",
            "Top intervention queue (by priority value proxy):",
        ]
    )
    lines.extend(queue_lines)
    lines.extend(
        [
            "",
            "## Validation Checks",
        ]
    )

    for row in validations.itertuples(index=False):
        lines.append(f"- {row.check_name}: {row.status} ({row.detail})")

    lines.extend(
        [
            "",
            "## Caveats and Limitations",
            "- Data is synthetic and behaviorally simulated; it supports method validation, not real-world attribution.",
            "- High-discount thresholds are policy assumptions and should be calibrated to commercial context.",
            "- Margin is a proxy using modeled unit cost, not full financial statement gross margin.",
            "- Outlier detection highlights governance signals, not proof of misconduct or causal drivers.",
            "",
            "## Recommendations and Next Steps",
        ]
    )

    for rec in recommendation_lines:
        lines.append(f"- {rec}")

    return "\n".join(lines)


def run_formal_pricing_analysis(
    processed_tables: Dict[str, pd.DataFrame],
    outputs_dir: Path,
    docs_dir: Path,
) -> Dict[str, pd.DataFrame]:
    outputs_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)

    pricing = processed_tables["order_item_pricing_metrics"].copy()
    customer_profile = processed_tables["customer_pricing_profile"].copy()
    customer_risk_scores = processed_tables.get("customer_risk_scores")

    pricing["order_date"] = pd.to_datetime(pricing["order_date"])
    pricing["year"] = pricing["order_date"].dt.year
    coverage_start = pricing["order_date"].min().strftime("%Y-%m-%d")
    coverage_end = pricing["order_date"].max().strftime("%Y-%m-%d")

    overall_health, yearly_health = _overall_pricing_health(pricing)
    dependency_tables = _discount_dependency(pricing, customer_profile)
    margin_risk = _margin_erosion_risk(pricing)
    inconsistency_tables = _pricing_inconsistency(pricing)
    product_patterns = _product_level_patterns(pricing)
    threshold_sensitivity = _build_threshold_sensitivity(pricing)
    governance_action_queue = _build_governance_action_queue(pricing, customer_risk_scores)
    verdict, verdict_reason = _pricing_health_verdict(overall_health.iloc[0])

    validations = _validation_checks(
        pricing=pricing,
        processed_tables=processed_tables,
        yearly_health=yearly_health,
        segment_dependency=dependency_tables["segment_discount_dependency"],
        overall_health=overall_health,
        customer_profile=customer_profile,
    )

    payload = {
        "overall_health": overall_health,
        "yearly_health": yearly_health,
        "analysis_window": {
            "coverage_start": coverage_start,
            "coverage_end": coverage_end,
        },
        "segment_dependency": dependency_tables["segment_discount_dependency"],
        "dependency_concentration": dependency_tables["discount_dependency_concentration"],
        "margin_erosion_risk": margin_risk,
        "rep_pricing_inconsistency": inconsistency_tables["rep_pricing_inconsistency"],
        "channel_region_inconsistency": inconsistency_tables["channel_region_pricing_inconsistency"],
        "product_patterns": product_patterns,
        "threshold_sensitivity": threshold_sensitivity,
        "governance_action_queue": governance_action_queue,
        "pricing_health_verdict": verdict,
        "pricing_health_reason": verdict_reason,
        "validation_checks": validations,
    }

    formal_report_md = _render_formal_report(payload)
    (outputs_dir / "formal_analysis_report.md").write_text(formal_report_md)
    (docs_dir / "formal_analysis_report.md").write_text(formal_report_md)

    overall_health.to_csv(outputs_dir / "overall_pricing_health.csv", index=False)
    yearly_health.to_csv(outputs_dir / "yearly_pricing_health.csv", index=False)

    dependency_tables["customer_discount_dependency"].to_csv(outputs_dir / "customer_discount_dependency.csv", index=False)
    dependency_tables["segment_discount_dependency"].to_csv(outputs_dir / "segment_discount_dependency.csv", index=False)
    dependency_tables["product_discount_dependency"].to_csv(outputs_dir / "product_discount_dependency.csv", index=False)
    dependency_tables["discount_dependency_concentration"].to_csv(
        outputs_dir / "discount_dependency_concentration.csv", index=False
    )

    margin_risk.to_csv(outputs_dir / "margin_erosion_risk.csv", index=False)
    inconsistency_tables["rep_pricing_inconsistency"].to_csv(outputs_dir / "rep_pricing_inconsistency.csv", index=False)
    inconsistency_tables["channel_region_pricing_inconsistency"].to_csv(
        outputs_dir / "channel_region_pricing_inconsistency.csv", index=False
    )
    inconsistency_tables["product_price_variance"].to_csv(outputs_dir / "product_price_variance.csv", index=False)
    product_patterns.to_csv(outputs_dir / "product_governance_patterns.csv", index=False)
    threshold_sensitivity.to_csv(outputs_dir / "threshold_sensitivity_analysis.csv", index=False)
    governance_action_queue.to_csv(outputs_dir / "governance_action_queue.csv", index=False)
    validations.to_csv(outputs_dir / "formal_analysis_validation_checks.csv", index=False)

    summary_payload = {
        "question": "Is the company growing with healthy pricing discipline, or relying on discounting patterns that erode margin?",
        "answer": verdict,
        "answer_detail": verdict_reason,
        "analysis_window": {
            "coverage_start": coverage_start,
            "coverage_end": coverage_end,
        },
        "overall_pricing_health": overall_health.iloc[0].to_dict(),
        "threshold_sensitivity": threshold_sensitivity.to_dict(orient="records"),
        "validation_status": {
            "all_checks_passed": bool((validations["status"] == "PASS").all()),
            "checks": len(validations),
        },
    }
    (outputs_dir / "formal_analysis_summary.json").write_text(json.dumps(summary_payload, indent=2))
    executive_summary = "\n".join(
        [
            "# Executive Summary",
            "",
            f"Pricing discipline verdict: {verdict}.",
            verdict_reason,
            f"- Time coverage: {coverage_start} to {coverage_end}",
            f"- Weighted realized discount: {overall_health.iloc[0]['weighted_realized_discount']:.2%}",
            f"- Price realization: {overall_health.iloc[0]['price_realization']:.2%}",
            f"- High-discount revenue share: {overall_health.iloc[0]['high_discount_revenue_share']:.2%}",
            f"- Validation checks passed: {(validations['status'] == 'PASS').sum()}/{len(validations)}",
        ]
    )
    (outputs_dir / "executive_summary.md").write_text(executive_summary)
    (docs_dir / "executive_summary.md").write_text(executive_summary)

    return {
        "overall_pricing_health": overall_health,
        "yearly_pricing_health": yearly_health,
        "customer_discount_dependency": dependency_tables["customer_discount_dependency"],
        "segment_discount_dependency": dependency_tables["segment_discount_dependency"],
        "product_discount_dependency": dependency_tables["product_discount_dependency"],
        "discount_dependency_concentration": dependency_tables["discount_dependency_concentration"],
        "margin_erosion_risk": margin_risk,
        "rep_pricing_inconsistency": inconsistency_tables["rep_pricing_inconsistency"],
        "channel_region_pricing_inconsistency": inconsistency_tables["channel_region_pricing_inconsistency"],
        "product_price_variance": inconsistency_tables["product_price_variance"],
        "product_governance_patterns": product_patterns,
        "threshold_sensitivity_analysis": threshold_sensitivity,
        "governance_action_queue": governance_action_queue,
        "formal_analysis_validation_checks": validations,
    }
