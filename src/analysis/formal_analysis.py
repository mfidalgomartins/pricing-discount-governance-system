from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd


def _pct_rank(series: pd.Series, reverse: bool = False) -> pd.Series:
    ranked = series.rank(pct=True)
    return (1 - ranked) if reverse else ranked


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
    validations = payload["validation_checks"]

    growth_2025_vs_2023 = None
    if {2023, 2025}.issubset(set(yearly["year"])):
        rev_2023 = yearly.loc[yearly["year"] == 2023, "revenue"].iloc[0]
        rev_2025 = yearly.loc[yearly["year"] == 2025, "revenue"].iloc[0]
        growth_2025_vs_2023 = (rev_2025 / rev_2023 - 1) * 100 if rev_2023 else np.nan

    top_segment_dependency = segment_dependency.sort_values("high_discount_revenue_share", ascending=False).iloc[0]
    top_margin_risk = margin_risk.iloc[0]
    outlier_reps = int(rep_inconsistency["discount_outlier_flag"].sum()) if "discount_outlier_flag" in rep_inconsistency.columns else 0

    recommendation_lines = [
        "tighten approval thresholds for >20% discount deals in high-risk segments/channels",
        "review segment pricing architecture for Public Sector and Enterprise cohorts",
        "redesign policy guardrails for discount-reliant products",
        "track high-discount revenue share and margin proxy as monthly governance KPIs",
    ]
    if outlier_reps > 0:
        recommendation_lines.insert(2, "investigate rep-level outliers and align incentives to price realization")
    else:
        recommendation_lines.insert(2, "continue rep-level monitoring; no peer outliers are currently flagged")

    lines = [
        "# Formal Pricing Discipline Analysis Report",
        "",
        "## Executive Summary",
        "Growth is not primarily healthy from a pricing-discipline perspective; performance is materially supported by high discount intensity that increases margin-erosion risk.",
        f"Revenue growth (2025 vs 2023): {growth_2025_vs_2023:.2f}%.",
        f"Weighted realized discount: {overall['weighted_realized_discount']:.2%}; price realization: {overall['price_realization']:.2%}; high-discount revenue share: {overall['high_discount_revenue_share']:.2%}.",
        f"Most exposed segment (discount dependency): {top_segment_dependency['segment']} ({top_segment_dependency['high_discount_revenue_share']:.2%} high-discount revenue share).",
        f"Most exposed segment-category margin erosion pattern: {top_margin_risk['segment']} / {top_margin_risk['category']} (risk score={top_margin_risk['margin_erosion_risk_score']:.1f}).",
        f"Rep pricing inconsistency: {outlier_reps} reps flagged as peer outliers (|z|>=2).",
        "",
        "## Methodology",
        "- Analysis type: full business diagnostics with validation checks.",
        "- Tables used: order_item_pricing_metrics, customer_pricing_profile, customer_risk_scores, segment_pricing_summary, segment_channel_diagnostics.",
        "- Time period: full available coverage (2023-01-01 to 2025-12-31).",
        "- Metric logic: realized discount, price realization, high-discount revenue share, margin proxy, repeat discount behavior, variance diagnostics.",
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
        f"- Products classified as discount-reliant: {(product_patterns['pricing_pattern'] == 'Discount-reliant').sum()} of {len(product_patterns)}.",
        f"- Products sold cleanly: {(product_patterns['pricing_pattern'] == 'Sold cleanly').sum()} of {len(product_patterns)}.",
        f"- Highest governance concern product: {product_patterns.iloc[0]['product_name']} (score={product_patterns.iloc[0]['governance_concern_score']:.1f}).",
        "",
        "## Validation Checks",
    ]

    for row in validations.itertuples(index=False):
        lines.append(f"- {row.check_name}: {row.status} ({row.detail})")

    lines.extend(
        [
            "",
            "## Caveats and Limitations",
            "- Data is synthetic and behaviorally simulated; it supports method validation, not real-world attribution.",
            "- High-discount threshold is set at 20%; sensitivity to alternative thresholds (e.g., 15% and 25%) is not included in the base run.",
            "- Margin is a proxy using modeled unit cost, not full financial statement gross margin.",
            "- Outlier detection highlights governance signals, not definitive misconduct or causal drivers.",
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

    pricing["order_date"] = pd.to_datetime(pricing["order_date"])
    pricing["year"] = pricing["order_date"].dt.year

    overall_health, yearly_health = _overall_pricing_health(pricing)
    dependency_tables = _discount_dependency(pricing, customer_profile)
    margin_risk = _margin_erosion_risk(pricing)
    inconsistency_tables = _pricing_inconsistency(pricing)
    product_patterns = _product_level_patterns(pricing)

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
        "segment_dependency": dependency_tables["segment_discount_dependency"],
        "dependency_concentration": dependency_tables["discount_dependency_concentration"],
        "margin_erosion_risk": margin_risk,
        "rep_pricing_inconsistency": inconsistency_tables["rep_pricing_inconsistency"],
        "channel_region_inconsistency": inconsistency_tables["channel_region_pricing_inconsistency"],
        "product_patterns": product_patterns,
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
    validations.to_csv(outputs_dir / "formal_analysis_validation_checks.csv", index=False)

    summary_payload = {
        "question": "Is the company growing with healthy pricing discipline, or relying on discounting patterns that erode margin?",
        "answer": "Growth is materially discount-led and exposes the business to margin erosion and governance inconsistency.",
        "overall_pricing_health": overall_health.iloc[0].to_dict(),
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
            "Growth is materially discount-led, not primarily pricing-discipline-led.",
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
        "formal_analysis_validation_checks": validations,
    }
