from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd


def _build_monthly_performance(pricing_metrics: pd.DataFrame) -> pd.DataFrame:
    monthly = (
        pricing_metrics.groupby("order_month", as_index=False)
        .agg(
            revenue=("line_revenue", "sum"),
            list_revenue=("line_list_revenue", "sum"),
            gross_margin_value=("gross_margin_value", "sum"),
            avg_discount_pct=("discount_depth", "mean"),
            high_discount_share=("high_discount_flag", "mean"),
        )
        .sort_values("order_month")
    )
    monthly["margin_proxy_pct"] = np.where(monthly["revenue"] > 0, monthly["gross_margin_value"] / monthly["revenue"], 0)
    monthly["discount_capture_gap"] = np.where(
        monthly["list_revenue"] > 0,
        1 - (monthly["revenue"] / monthly["list_revenue"]),
        0,
    )
    return monthly


def _build_descriptive_tables(pricing_metrics: pd.DataFrame, segment_summary: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    channel_summary = (
        pricing_metrics.groupby("sales_channel", as_index=False)
        .agg(
            revenue=("line_revenue", "sum"),
            avg_discount_pct=("discount_depth", "mean"),
            avg_margin_proxy_pct=("margin_proxy_pct", "mean"),
            high_discount_share=("high_discount_flag", "mean"),
        )
        .sort_values("avg_discount_pct", ascending=False)
    )

    product_summary = (
        pricing_metrics.groupby(["product_id", "product_name", "category"], as_index=False)
        .agg(
            revenue=("line_revenue", "sum"),
            avg_discount_pct=("discount_depth", "mean"),
            avg_margin_proxy_pct=("margin_proxy_pct", "mean"),
            high_discount_share=("high_discount_flag", "mean"),
        )
        .sort_values("revenue", ascending=False)
    )

    segment_ranked = segment_summary.sort_values("margin_erosion_proxy", ascending=False)
    return {
        "channel_pricing_summary": channel_summary,
        "product_pricing_summary": product_summary,
        "segment_pricing_summary_ranked": segment_ranked,
    }


def _build_diagnostic_tables(pricing_metrics: pd.DataFrame, customer_risk_scores: pd.DataFrame) -> Dict[str, pd.DataFrame]:
    rep_diagnostics = (
        pricing_metrics.groupby(["sales_rep_id", "team", "rep_region"], as_index=False)
        .agg(
            revenue=("line_revenue", "sum"),
            avg_discount_pct=("discount_depth", "mean"),
            avg_margin_proxy_pct=("margin_proxy_pct", "mean"),
            high_discount_share=("high_discount_flag", "mean"),
            active_customers=("customer_id", pd.Series.nunique),
            order_lines=("order_item_id", "count"),
        )
        .query("order_lines >= 80")
        .sort_values("avg_discount_pct", ascending=False)
    )

    top_risk_customers = customer_risk_scores.head(50).copy()

    risk_by_segment = (
        customer_risk_scores.groupby(["segment", "risk_tier"], as_index=False)
        .agg(
            customers=("customer_id", "count"),
            revenue=("total_revenue", "sum"),
            avg_priority=("governance_priority_score", "mean"),
        )
        .sort_values(["segment", "avg_priority"], ascending=[True, False])
    )

    return {
        "rep_pricing_diagnostics": rep_diagnostics,
        "top_risk_customers": top_risk_customers,
        "risk_by_segment": risk_by_segment,
    }


def _build_findings(
    monthly: pd.DataFrame,
    segment_summary: pd.DataFrame,
    channel_summary: pd.DataFrame,
    customer_risk_scores: pd.DataFrame,
) -> dict:
    yearly = monthly.assign(year=monthly["order_month"].str[:4]).groupby("year", as_index=False).agg(
        revenue=("revenue", "sum"),
        list_revenue=("list_revenue", "sum"),
        gross_margin_value=("gross_margin_value", "sum"),
    )
    yearly["margin_proxy_pct"] = np.where(
        yearly["revenue"] > 0,
        yearly["gross_margin_value"] / yearly["revenue"],
        np.nan,
    )
    yearly["avg_discount_pct"] = np.where(
        yearly["list_revenue"] > 0,
        1 - (yearly["revenue"] / yearly["list_revenue"]),
        np.nan,
    )

    if {"2023", "2025"}.issubset(set(yearly["year"])):
        rev_2023 = float(yearly.loc[yearly["year"] == "2023", "revenue"].iloc[0])
        rev_2025 = float(yearly.loc[yearly["year"] == "2025", "revenue"].iloc[0])
        growth_2025_vs_2023 = (rev_2025 / rev_2023 - 1) * 100 if rev_2023 else np.nan
    else:
        growth_2025_vs_2023 = np.nan

    top_erosion_segment = segment_summary.sort_values("margin_erosion_proxy", ascending=False).iloc[0]
    highest_discount_channel = channel_summary.sort_values("avg_discount_pct", ascending=False).iloc[0]

    critical = customer_risk_scores[customer_risk_scores["risk_tier"] == "Critical"]
    high_or_critical = customer_risk_scores[customer_risk_scores["risk_tier"].isin(["High", "Critical"])]

    findings = {
        "revenue_growth_2025_vs_2023_pct": round(float(growth_2025_vs_2023), 2) if not np.isnan(growth_2025_vs_2023) else None,
        "latest_year_avg_discount_pct": round(float(yearly.sort_values("year").iloc[-1]["avg_discount_pct"]), 4),
        "latest_year_avg_margin_proxy_pct": round(float(yearly.sort_values("year").iloc[-1]["margin_proxy_pct"]), 4),
        "segment_with_highest_margin_erosion_proxy": top_erosion_segment["segment"],
        "segment_margin_erosion_proxy_value": round(float(top_erosion_segment["margin_erosion_proxy"]), 2),
        "channel_with_highest_avg_discount": highest_discount_channel["sales_channel"],
        "channel_highest_avg_discount_pct": round(float(highest_discount_channel["avg_discount_pct"]), 4),
        "critical_risk_customers": int(len(critical)),
        "high_or_critical_customers": int(len(high_or_critical)),
        "high_or_critical_revenue_share": round(
            float(high_or_critical["total_revenue"].sum() / customer_risk_scores["total_revenue"].sum()), 4
        ),
    }

    recommendations = [
        "tighten approval thresholds for deals above 20% discount in high-risk segments",
        "review segment pricing where margin erosion proxy is highest before next planning cycle",
        "investigate rep behavior for outlier discount variance by team and region",
        "redesign discount policy for customers with sustained high discount dependency",
        "monitor only low-risk cohorts with monthly governance reporting",
    ]

    return {
        "findings": findings,
        "recommendations": recommendations,
    }


def _render_executive_summary(findings_payload: dict) -> str:
    findings = findings_payload["findings"]
    recommendations = findings_payload["recommendations"]
    growth_value = findings["revenue_growth_2025_vs_2023_pct"]
    growth_line = (
        f"{growth_value:.2f}%"
        if growth_value is not None
        else "N/A for current date window"
    )

    lines = [
        "# Pricing & Discount Governance Executive Summary",
        "",
        "## Core Question",
        "Is growth supported by pricing discipline, or by discount behaviors that erode margin and weaken governance?",
        "",
        "## Key Findings",
        f"- Revenue growth (2025 vs 2023): {growth_line}.",
        f"- Latest-year average discount: {findings['latest_year_avg_discount_pct']:.2%}.",
        f"- Latest-year average margin proxy: {findings['latest_year_avg_margin_proxy_pct']:.2%}.",
        f"- Highest margin erosion segment: {findings['segment_with_highest_margin_erosion_proxy']} (proxy={findings['segment_margin_erosion_proxy_value']}).",
        f"- Highest discount channel: {findings['channel_with_highest_avg_discount']} ({findings['channel_highest_avg_discount_pct']:.2%}).",
        f"- High/Critical customers: {findings['high_or_critical_customers']} (revenue share={findings['high_or_critical_revenue_share']:.2%}).",
        "",
        "## Recommended Actions",
    ]

    for rec in recommendations:
        lines.append(f"- {rec}")

    lines.append("")
    lines.append("## Caveat")
    lines.append("Synthetic data was engineered to mimic realistic commercial behavior; conclusions illustrate governance methodology, not a real firm's performance.")

    return "\n".join(lines)


def generate_analysis_outputs(
    feature_tables: Dict[str, pd.DataFrame],
    risk_tables: Dict[str, pd.DataFrame],
    outputs_dir: Path,
) -> Dict[str, pd.DataFrame]:
    outputs_dir.mkdir(parents=True, exist_ok=True)

    pricing_metrics = feature_tables["order_item_pricing_metrics"]
    segment_summary = feature_tables["segment_pricing_summary"]
    customer_risk_scores = risk_tables["customer_risk_scores"]

    monthly = _build_monthly_performance(pricing_metrics)
    descriptive = _build_descriptive_tables(pricing_metrics, segment_summary)
    diagnostics = _build_diagnostic_tables(pricing_metrics, customer_risk_scores)

    findings_payload = _build_findings(
        monthly=monthly,
        segment_summary=segment_summary,
        channel_summary=descriptive["channel_pricing_summary"],
        customer_risk_scores=customer_risk_scores,
    )

    executive_summary_md = _render_executive_summary(findings_payload)
    (outputs_dir / "executive_summary.md").write_text(executive_summary_md)
    (outputs_dir / "key_findings.json").write_text(json.dumps(findings_payload, indent=2))

    monthly.to_csv(outputs_dir / "monthly_pricing_performance.csv", index=False)
    descriptive["channel_pricing_summary"].to_csv(outputs_dir / "channel_pricing_summary.csv", index=False)
    descriptive["product_pricing_summary"].to_csv(outputs_dir / "product_pricing_summary.csv", index=False)
    diagnostics["rep_pricing_diagnostics"].to_csv(outputs_dir / "rep_pricing_diagnostics.csv", index=False)
    diagnostics["top_risk_customers"].to_csv(outputs_dir / "top_risk_customers.csv", index=False)
    diagnostics["risk_by_segment"].to_csv(outputs_dir / "risk_by_segment.csv", index=False)

    analysis_tables = {
        "monthly_pricing_performance": monthly,
        "channel_pricing_summary": descriptive["channel_pricing_summary"],
        "product_pricing_summary": descriptive["product_pricing_summary"],
        "rep_pricing_diagnostics": diagnostics["rep_pricing_diagnostics"],
        "top_risk_customers": diagnostics["top_risk_customers"],
        "risk_by_segment": diagnostics["risk_by_segment"],
    }
    return analysis_tables
