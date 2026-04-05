from __future__ import annotations

from pathlib import Path
from typing import Dict

import matplotlib
import numpy as np
import pandas as pd
import seaborn as sns
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter


def _currency_millions(x: float, _pos: int) -> str:
    return f"${x/1_000_000:.1f}M"


def _percent_axis(x: float, _pos: int) -> str:
    return f"{x:.0f}%"


def _currency_units(x: float, _pos: int) -> str:
    return f"${x:,.0f}"


def _save(fig: plt.Figure, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)


def create_visualization_pack(
    processed_tables: Dict[str, pd.DataFrame],
    outputs_dir: Path,
    docs_dir: Path,
) -> Dict[str, pd.DataFrame]:
    viz_dir = outputs_dir / "visualizations"
    viz_dir.mkdir(parents=True, exist_ok=True)
    docs_dir.mkdir(parents=True, exist_ok=True)

    pricing = processed_tables["order_item_pricing_metrics"].copy()
    customer_risk = processed_tables["customer_risk_scores"].copy()
    segment_summary = processed_tables["segment_pricing_summary"].copy()

    pricing["order_date"] = pd.to_datetime(pricing["order_date"])
    pricing["order_month_date"] = pd.to_datetime(pricing["order_month"])
    pricing["discount_pct_100"] = pricing["discount_depth"] * 100

    sns.set_theme(style="whitegrid", context="talk")

    chart_manifest: list[dict] = []

    # 1) Discount distribution
    fig, ax = plt.subplots(figsize=(11, 6))
    sns.histplot(pricing["discount_pct_100"], bins=45, color="#0b7285", alpha=0.85, ax=ax)
    median_discount = pricing["discount_pct_100"].median()
    p90_discount = pricing["discount_pct_100"].quantile(0.90)
    discount_title = (
        "Discount Distribution Shows a Material Deep-Discount Tail"
        if (median_discount >= 15 or p90_discount >= 30)
        else "Discount Distribution Remains Moderately Concentrated"
    )
    ax.axvline(median_discount, color="#e03131", linestyle="--", linewidth=2, label=f"Median: {median_discount:.1f}%")
    ax.axvline(p90_discount, color="#f08c00", linestyle=":", linewidth=2, label=f"P90: {p90_discount:.1f}%")
    ax.set_title(discount_title)
    ax.set_xlabel("Discount depth (%)")
    ax.set_ylabel("Order item count")
    ax.legend(frameon=False)
    ax.xaxis.set_major_formatter(FuncFormatter(_percent_axis))
    _save(fig, viz_dir / "discount_distribution.png")
    chart_manifest.append(
        {
            "chart_file": "discount_distribution.png",
            "chart_type": "distribution histogram",
            "why_appropriate": "Shows concentration and spread of discount depth across all transactions.",
            "insight_focus": "Discount distribution",
        }
    )

    # 2) Realized price vs list price
    fig, ax = plt.subplots(figsize=(11, 7))
    sample = pricing.sample(min(20000, len(pricing)), random_state=42)
    hb = ax.hexbin(
        sample["list_price_at_sale"],
        sample["realized_price"],
        gridsize=55,
        cmap="YlGnBu",
        mincnt=1,
    )
    max_val = max(sample["list_price_at_sale"].max(), sample["realized_price"].max())
    ax.plot([0, max_val], [0, max_val], linestyle="--", linewidth=2, color="#d9480f", label="Parity: realized=list")
    ax.set_title("Realized vs List Price Relationship (Transaction Density)")
    ax.set_xlabel("List price at sale")
    ax.set_ylabel("Realized unit price")
    ax.xaxis.set_major_formatter(FuncFormatter(_currency_units))
    ax.yaxis.set_major_formatter(FuncFormatter(_currency_units))
    ax.legend(frameon=False)
    cb = fig.colorbar(hb, ax=ax)
    cb.set_label("Transaction density")
    _save(fig, viz_dir / "realized_price_vs_list_price.png")
    chart_manifest.append(
        {
            "chart_file": "realized_price_vs_list_price.png",
            "chart_type": "hexbin correlation",
            "why_appropriate": "Compares two continuous price fields at high volume without overplotting.",
            "insight_focus": "Realized price versus list price",
        }
    )

    # 3) High-risk segment comparison
    risk_segment = (
        customer_risk.assign(high_risk=customer_risk["risk_tier"].isin(["High", "Critical"]).astype(int))
        .groupby("segment", as_index=False)
        .agg(
            high_risk_customer_share=("high_risk", "mean"),
            high_risk_customers=("high_risk", "sum"),
            total_customers=("customer_id", "count"),
        )
    )
    seg = segment_summary.merge(risk_segment, on="segment", how="left")
    seg = seg.sort_values("margin_erosion_proxy", ascending=False)

    segment_title = (
        f"{seg.iloc[0]['segment']} and {seg.iloc[1]['segment']} Have the Highest Margin Erosion Exposure"
        if len(seg) >= 2
        else "Segment Margin Erosion Exposure and High-Risk Concentration"
    )

    fig, ax = plt.subplots(figsize=(11, 6.5))
    ax.bar(seg["segment"], seg["margin_erosion_proxy"], color="#364fc7", alpha=0.85, label="Margin erosion proxy")
    ax.plot(
        seg["segment"],
        seg["high_risk_customer_share"] * 100,
        marker="o",
        linewidth=2.5,
        color="#e03131",
        label="High-risk customer share",
    )
    ax.set_ylabel("Percent / index")
    ax.set_xlabel("Segment")
    ax.set_title(segment_title)
    ax.yaxis.set_major_formatter(FuncFormatter(_percent_axis))
    ax.legend(frameon=False, loc="upper right")
    _save(fig, viz_dir / "high_risk_segments_comparison.png")
    chart_manifest.append(
        {
            "chart_file": "high_risk_segments_comparison.png",
            "chart_type": "dual-axis category comparison",
            "why_appropriate": "Compares segment-level erosion intensity and risk concentration in one view.",
            "insight_focus": "High-risk segments comparison",
        }
    )

    # 4) Revenue under high discount
    monthly_comp = (
        pricing.groupby(["order_month_date", "high_discount_flag"], as_index=False)["line_revenue"].sum()
        .pivot(index="order_month_date", columns="high_discount_flag", values="line_revenue")
        .fillna(0)
        .rename(columns={0: "standard_discount_revenue", 1: "high_discount_revenue"})
        .reset_index()
    )

    total_high_discount_revenue = float(monthly_comp["high_discount_revenue"].sum())
    total_revenue = float(
        monthly_comp["high_discount_revenue"].sum() + monthly_comp["standard_discount_revenue"].sum()
    )
    high_discount_revenue_share = total_high_discount_revenue / total_revenue if total_revenue else np.nan
    revenue_title = (
        "High-Discount Deals Represent a Material Share of Monthly Revenue"
        if high_discount_revenue_share >= 0.25
        else "High-Discount Revenue Share Remains Limited Over Time"
    )

    fig, ax = plt.subplots(figsize=(12, 6.5))
    ax.stackplot(
        monthly_comp["order_month_date"],
        monthly_comp["standard_discount_revenue"],
        monthly_comp["high_discount_revenue"],
        labels=["<20% discount", ">=20% discount"],
        colors=["#74c0fc", "#fa5252"],
        alpha=0.9,
    )
    ax.set_title(revenue_title)
    ax.set_xlabel("Order month")
    ax.set_ylabel("Revenue")
    ax.yaxis.set_major_formatter(FuncFormatter(_currency_millions))
    ax.legend(frameon=False, loc="upper left")
    _save(fig, viz_dir / "revenue_under_high_discount.png")
    chart_manifest.append(
        {
            "chart_file": "revenue_under_high_discount.png",
            "chart_type": "stacked area trend",
            "why_appropriate": "Shows composition and trend of revenue by discount intensity over time.",
            "insight_focus": "Revenue under high discount",
        }
    )

    # 5) Channel pricing comparison
    channel_cmp = (
        pricing.groupby("sales_channel", as_index=False)
        .agg(
            revenue=("line_revenue", "sum"),
            avg_discount_pct=("discount_depth", "mean"),
            avg_margin_proxy_pct=("margin_proxy_pct", "mean"),
        )
        .sort_values("avg_discount_pct", ascending=False)
    )
    top_channels = channel_cmp.head(2)["sales_channel"].tolist()
    channel_title = (
        f"{' and '.join(top_channels)} Channels Carry the Highest Discount Burden"
        if len(top_channels) == 2
        else "Channel Discount Burden Comparison"
    )

    fig, ax = plt.subplots(figsize=(11, 6.5))
    sns.barplot(
        data=channel_cmp,
        x="sales_channel",
        y="avg_discount_pct",
        hue="sales_channel",
        palette=["#f03e3e", "#fa8c16", "#339af0", "#2f9e44"],
        legend=False,
        ax=ax,
    )
    ax.set_title(channel_title)
    ax.set_xlabel("Sales channel")
    ax.set_ylabel("Average discount (%)")
    ax.yaxis.set_major_formatter(FuncFormatter(lambda x, _p: f"{x*100:.0f}%"))

    for i, row in channel_cmp.reset_index().iterrows():
        ax.text(i, row["avg_discount_pct"] + 0.004, f"Margin {row['avg_margin_proxy_pct']*100:.1f}%", ha="center", va="bottom", fontsize=9)

    _save(fig, viz_dir / "channel_pricing_comparison.png")
    chart_manifest.append(
        {
            "chart_file": "channel_pricing_comparison.png",
            "chart_type": "category comparison bar",
            "why_appropriate": "Compares discount intensity across discrete commercial channels.",
            "insight_focus": "Channel pricing comparison",
        }
    )

    # 6) Product pricing dependence ranking
    product_dep = (
        pricing.groupby(["product_id", "product_name", "category"], as_index=False)
        .agg(
            revenue=("line_revenue", "sum"),
            high_discount_revenue=("line_revenue", lambda s: s[pricing.loc[s.index, "high_discount_flag"] == 1].sum()),
            avg_discount_pct=("discount_depth", "mean"),
            avg_margin_proxy_pct=("margin_proxy_pct", "mean"),
        )
        .sort_values("revenue", ascending=False)
    )
    product_dep["high_discount_revenue_share"] = np.where(
        product_dep["revenue"] > 0,
        product_dep["high_discount_revenue"] / product_dep["revenue"],
        0,
    )
    product_dep["dependence_score"] = product_dep["high_discount_revenue_share"] * np.log1p(product_dep["revenue"])
    top_dep = product_dep.sort_values("dependence_score", ascending=False).head(15).sort_values("dependence_score")
    max_dependency_share = float(top_dep["high_discount_revenue_share"].max()) if not top_dep.empty else 0.0
    product_title = (
        "Top Products Show Material Reliance on Discounted Revenue"
        if max_dependency_share >= 0.40
        else "Top Products by Discounted-Revenue Reliance"
    )

    fig, ax = plt.subplots(figsize=(12, 8))
    bars = ax.barh(top_dep["product_name"], top_dep["dependence_score"], color="#5f3dc4", alpha=0.9)
    ax.set_title(product_title)
    ax.set_xlabel("Discount dependence ranking score")
    ax.set_ylabel("Product")

    for i, row in enumerate(top_dep.itertuples(index=False)):
        ax.text(
            row.dependence_score + 0.01,
            i,
            f"{row.high_discount_revenue_share*100:.0f}% high-discount revenue",
            va="center",
            fontsize=9,
        )

    _save(fig, viz_dir / "product_pricing_dependence_ranking.png")
    chart_manifest.append(
        {
            "chart_file": "product_pricing_dependence_ranking.png",
            "chart_type": "ranking bar",
            "why_appropriate": "Ranks products by discount dependency intensity to prioritize governance action.",
            "insight_focus": "Product pricing dependence ranking",
        }
    )

    manifest_df = pd.DataFrame(chart_manifest)
    manifest_df.to_csv(viz_dir / "visualization_manifest.csv", index=False)

    markdown_lines = [
        "# Publication-Quality Visualization Pack",
        "",
        "The charts below are generated from processed project outputs and designed for executive communication.",
        "",
    ]

    for row in manifest_df.itertuples(index=False):
        markdown_lines.append(f"## {row.insight_focus}")
        markdown_lines.append(f"- Chart file: `outputs/visualizations/{row.chart_file}`")
        markdown_lines.append(f"- Chart type: {row.chart_type}")
        markdown_lines.append(f"- Why this type: {row.why_appropriate}")
        markdown_lines.append("")

    viz_doc = "\n".join(markdown_lines)
    (outputs_dir / "visualization_pack.md").write_text(viz_doc)
    (docs_dir / "visualization_pack.md").write_text(viz_doc)

    return {
        "visualization_manifest": manifest_df,
        "segment_risk_visual_base": seg,
        "channel_pricing_visual_base": channel_cmp,
        "product_dependence_visual_base": product_dep,
    }
