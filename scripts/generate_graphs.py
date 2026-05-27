"""
Generate analytical graphs for the Pricing Discount Governance System.

Outputs 9 PNG files to outputs/Graphs/.

Run with:
    python scripts/generate_graphs.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import matplotlib
matplotlib.use("Agg")  # non-interactive backend

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Make project importable when run from any working directory
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.ingestion.synthetic_data import SyntheticDataConfig, generate_synthetic_business_data
from src.processing.build_base_tables import build_order_item_enriched
from src.features.pricing_features import build_feature_tables
from src.scoring.risk_scoring import build_risk_outputs

# ---------------------------------------------------------------------------
# Design tokens (mirrors dashboard CSS variables)
# ---------------------------------------------------------------------------
PAPER       = "#f4f1ea"
INK         = "#1a1a1a"
INK_LIGHT   = "#6b6b6b"
RISK        = "#8c2920"   # critical / oxblood
WARN        = "#936323"   # warning / amber
OK          = "#3c5d2e"   # healthy / forest green
INFO        = "#1a1a1a"   # neutral / ink
RISK_SOFT   = "#f5e6e4"
WARN_SOFT   = "#f5eedf"
OK_SOFT     = "#e6efe3"
SEGMENT_PALETTE = ["#8c2920", "#936323", "#3c5d2e", "#2a4a7a", "#5a3472", "#1a5a6b"]

FONT_FAMILY = "DejaVu Sans"  # safe fallback — IBM Plex not guaranteed installed

plt.rcParams.update({
    "figure.facecolor":  PAPER,
    "axes.facecolor":    PAPER,
    "axes.edgecolor":    INK,
    "axes.labelcolor":   INK,
    "text.color":        INK,
    "xtick.color":       INK_LIGHT,
    "ytick.color":       INK_LIGHT,
    "grid.color":        "#d8d4cc",
    "grid.linewidth":    0.5,
    "axes.spines.top":   False,
    "axes.spines.right": False,
    "font.family":       FONT_FAMILY,
    "axes.titlesize":    13,
    "axes.titleweight":  "bold",
    "axes.labelsize":    10,
    "xtick.labelsize":   9,
    "ytick.labelsize":   9,
    "legend.fontsize":   9,
    "figure.dpi":        150,
    "savefig.dpi":       150,
    "savefig.bbox":      "tight",
    "savefig.facecolor": PAPER,
})

OUT_DIR = PROJECT_ROOT / "outputs" / "Graphs"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------
def _save(fig: plt.Figure, name: str) -> Path:
    path = OUT_DIR / name
    fig.savefig(path)
    plt.close(fig)
    print(f"  saved → {path.relative_to(PROJECT_ROOT)}")
    return path


def _fmt_currency(x: float, _pos=None) -> str:
    if x >= 1_000_000:
        return f"${x/1_000_000:.1f}M"
    if x >= 1_000:
        return f"${x/1_000:.0f}K"
    return f"${x:.0f}"


def _fmt_pct(x: float, _pos=None) -> str:
    return f"{x*100:.0f}%"


# ---------------------------------------------------------------------------
# Data pipeline
# ---------------------------------------------------------------------------
def build_data() -> dict:
    print("Running pipeline (seed=42, 2 000 orders)…")
    config = SyntheticDataConfig(
        seed=42,
        n_customers=200,
        n_products=20,
        n_sales_reps=12,
        n_orders=2_000,
        start_date="2024-01-01",
        end_date="2024-12-31",
    )
    raw        = generate_synthetic_business_data(config)
    enriched   = build_order_item_enriched(raw)
    features   = build_feature_tables(enriched)
    risk       = build_risk_outputs(features)
    metrics    = features["order_item_pricing_metrics"]
    return {
        "metrics":            metrics,
        "customer_profile":   features["customer_pricing_profile"],
        "segment_summary":    features["segment_pricing_summary"],
        "seg_channel":        features["segment_channel_diagnostics"],
        "customer_risk":      risk["customer_risk_scores"],
        "risk_tier_summary":  risk["risk_tier_summary"],
        "main_driver":        risk["main_driver_summary"],
    }


# ===========================================================================
# CHART 1 — Monthly Revenue Trend + High-Discount Share
# ===========================================================================
def chart_monthly_revenue(metrics: pd.DataFrame) -> None:
    m = metrics.copy()
    m["month"] = m["order_date"].dt.to_period("M").dt.to_timestamp()

    monthly = m.groupby("month").agg(
        revenue=("line_revenue", "sum"),
        hd_revenue=("line_revenue", lambda s: s[m.loc[s.index, "high_discount_flag"] == 1].sum()),
    ).reset_index()
    monthly["hd_share"] = monthly["hd_revenue"] / monthly["revenue"]

    fig, ax1 = plt.subplots(figsize=(10, 4.5))
    ax2 = ax1.twinx()

    ax1.fill_between(monthly["month"], monthly["revenue"], color=INFO, alpha=0.07)
    ax1.plot(monthly["month"], monthly["revenue"], color=INK, lw=2, marker="o", ms=4, label="Total Revenue")
    ax2.plot(monthly["month"], monthly["hd_share"], color=RISK, lw=1.5, ls="--", marker="s", ms=3, label="High-Discount Share")

    ax1.set_title("Monthly Revenue & High-Discount Revenue Share")
    ax1.set_xlabel("")
    ax1.set_ylabel("Revenue", color=INK)
    ax2.set_ylabel("High-Discount Share", color=RISK)
    ax1.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt_currency))
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt_pct))
    ax2.tick_params(colors=RISK)
    ax2.spines["right"].set_visible(True)
    ax2.spines["right"].set_color(RISK)
    ax1.tick_params(axis="x", rotation=30)
    ax1.grid(axis="y")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left", framealpha=0.85)

    _save(fig, "01_monthly_revenue_trend.png")


# ===========================================================================
# CHART 2 — Discount Depth Distribution (histogram)
# ===========================================================================
def chart_discount_distribution(metrics: pd.DataFrame) -> None:
    fig, ax = plt.subplots(figsize=(8, 4))
    bins = np.linspace(0, 0.5, 51)
    ax.hist(metrics["discount_depth"].clip(upper=0.5), bins=bins, color=INK, alpha=0.75, edgecolor=PAPER, linewidth=0.3)

    threshold = 0.20
    ax.axvline(threshold, color=RISK, lw=1.5, ls="--", label=f"High-discount threshold ({threshold:.0%})")
    ax.set_title("Discount Depth Distribution (Order-Item Level)")
    ax.set_xlabel("Discount Depth")
    ax.set_ylabel("Order Items")
    ax.xaxis.set_major_formatter(mticker.FuncFormatter(_fmt_pct))
    ax.grid(axis="y")
    ax.legend()

    pct_hd = (metrics["high_discount_flag"] == 1).mean()
    ax.text(0.99, 0.96, f"High-discount items: {pct_hd:.1%}",
            transform=ax.transAxes, ha="right", va="top",
            fontsize=9, color=RISK)

    _save(fig, "02_discount_depth_distribution.png")


# ===========================================================================
# CHART 3 — Revenue by Discount Bucket
# ===========================================================================
def chart_revenue_by_bucket(metrics: pd.DataFrame) -> None:
    bucket_order = ["0-5%", "5-10%", "10-20%", "20-30%", "30%+"]
    agg = (
        metrics.groupby("discount_bucket")["line_revenue"]
        .sum()
        .reindex(bucket_order)
        .fillna(0)
    )
    total = agg.sum()
    colors = [OK, OK, WARN, RISK, RISK]

    fig, ax = plt.subplots(figsize=(8, 4))
    bars = ax.bar(agg.index, agg.values, color=colors, width=0.6, edgecolor=PAPER, linewidth=0.5)

    for bar, val in zip(bars, agg.values):
        pct = val / total
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + total * 0.005,
                f"{pct:.1%}", ha="center", va="bottom", fontsize=9, color=INK)

    ax.set_title("Revenue by Discount Bucket")
    ax.set_xlabel("Discount Bucket")
    ax.set_ylabel("Revenue")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt_currency))
    ax.grid(axis="y")

    _save(fig, "03_revenue_by_discount_bucket.png")


# ===========================================================================
# CHART 4 — Margin Proxy by Discount Bucket (box plot)
# ===========================================================================
def chart_margin_by_bucket(metrics: pd.DataFrame) -> None:
    bucket_order = ["0-5%", "5-10%", "10-20%", "20-30%", "30%+"]
    groups = [
        metrics.loc[metrics["discount_bucket"] == b, "margin_proxy_pct"].dropna().values
        for b in bucket_order
    ]
    colors = [OK, OK, WARN, RISK, RISK]

    fig, ax = plt.subplots(figsize=(8, 4.5))
    bp = ax.boxplot(groups, tick_labels=bucket_order, patch_artist=True,
                    medianprops=dict(color="white", linewidth=2),
                    whiskerprops=dict(color=INK_LIGHT),
                    capprops=dict(color=INK_LIGHT),
                    flierprops=dict(marker=".", color=INK_LIGHT, markersize=3, alpha=0.5))

    for patch, color in zip(bp["boxes"], colors):
        patch.set_facecolor(color)
        patch.set_alpha(0.75)

    ax.axhline(0.45, color=INK_LIGHT, lw=1, ls=":", label="Healthy margin floor (45%)")
    ax.set_title("Gross Margin Proxy by Discount Bucket")
    ax.set_xlabel("Discount Bucket")
    ax.set_ylabel("Margin Proxy %")
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt_pct))
    ax.grid(axis="y")
    ax.legend()

    _save(fig, "04_margin_by_discount_bucket.png")


# ===========================================================================
# CHART 5 — Segment Pricing Health (avg discount vs avg margin)
# ===========================================================================
def chart_segment_health(segment_summary: pd.DataFrame) -> None:
    seg = segment_summary.copy().sort_values("avg_discount_pct", ascending=True)
    x = np.arange(len(seg))
    w = 0.38

    fig, ax = plt.subplots(figsize=(9, 4.5))
    ax2 = ax.twinx()

    bars1 = ax.bar(x - w / 2, seg["avg_discount_pct"], width=w,
                   color=RISK, alpha=0.80, label="Avg Discount %")
    bars2 = ax2.bar(x + w / 2, seg["avg_margin_proxy_pct"], width=w,
                    color=OK, alpha=0.80, label="Avg Margin Proxy %")

    ax.set_xticks(x)
    ax.set_xticklabels(seg["segment"], rotation=20, ha="right")
    ax.set_ylabel("Avg Discount", color=RISK)
    ax2.set_ylabel("Avg Margin Proxy", color=OK)
    ax.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt_pct))
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt_pct))
    ax.tick_params(axis="y", colors=RISK)
    ax2.tick_params(axis="y", colors=OK)
    ax2.spines["right"].set_visible(True)
    ax2.spines["right"].set_color(OK)
    ax.set_title("Segment Pricing Health — Avg Discount vs Avg Margin")
    ax.grid(axis="y", alpha=0.5)

    h1, l1 = ax.get_legend_handles_labels()
    h2, l2 = ax2.get_legend_handles_labels()
    ax.legend(h1 + h2, l1 + l2, loc="upper left", framealpha=0.85)

    _save(fig, "05_segment_pricing_health.png")


# ===========================================================================
# CHART 6 — Channel × Segment Discount Heatmap
# ===========================================================================
def chart_channel_segment_heatmap(seg_channel: pd.DataFrame) -> None:
    pivot = seg_channel.pivot_table(
        index="sales_channel", columns="segment", values="avg_discount_pct", aggfunc="mean"
    )

    fig, ax = plt.subplots(figsize=(max(7, len(pivot.columns) * 1.3), max(3.5, len(pivot) * 0.8)))
    im = ax.imshow(pivot.values, cmap="RdYlGn_r", aspect="auto", vmin=0.05, vmax=0.35)

    ax.set_xticks(range(len(pivot.columns)))
    ax.set_yticks(range(len(pivot.index)))
    ax.set_xticklabels(pivot.columns, rotation=30, ha="right")
    ax.set_yticklabels(pivot.index)

    for i in range(len(pivot.index)):
        for j in range(len(pivot.columns)):
            val = pivot.values[i, j]
            if not np.isnan(val):
                ax.text(j, i, f"{val:.1%}", ha="center", va="center",
                        fontsize=9, color="white" if val > 0.22 else INK, fontweight="bold")

    cbar = fig.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    cbar.set_label("Avg Discount %", rotation=270, labelpad=12)
    cbar.ax.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt_pct))

    ax.set_title("Avg Discount % — Channel × Segment")
    ax.set_xlabel("Customer Segment")
    ax.set_ylabel("Sales Channel")
    fig.tight_layout()

    _save(fig, "06_channel_segment_discount_heatmap.png")


# ===========================================================================
# CHART 7 — Customer Risk Tier Breakdown (count + revenue)
# ===========================================================================
def chart_risk_tier(customer_risk: pd.DataFrame) -> None:
    tier_order = ["Critical", "High", "Medium", "Low"]
    tier_colors = {
        "Critical": RISK,
        "High":     WARN,
        "Medium":   "#c8a800",
        "Low":      OK,
    }

    agg = (
        customer_risk.groupby("risk_tier")
        .agg(customers=("customer_id", "count"), revenue=("total_revenue", "sum"))
        .reindex(tier_order)
        .fillna(0)
        .reset_index()
    )
    colors = [tier_colors[t] for t in agg["risk_tier"]]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(11, 4.5))

    ax1.bar(agg["risk_tier"], agg["customers"], color=colors, edgecolor=PAPER, linewidth=0.5)
    for i, (_, row) in enumerate(agg.iterrows()):
        ax1.text(i, row["customers"] + 0.5, f"{int(row['customers'])}", ha="center", va="bottom", fontsize=10)
    ax1.set_title("Customer Count by Risk Tier")
    ax1.set_ylabel("Customers")
    ax1.grid(axis="y")

    ax2.bar(agg["risk_tier"], agg["revenue"], color=colors, edgecolor=PAPER, linewidth=0.5)
    total_rev = agg["revenue"].sum()
    for i, (_, row) in enumerate(agg.iterrows()):
        ax2.text(i, row["revenue"] + total_rev * 0.01,
                 f"{row['revenue']/total_rev:.1%}", ha="center", va="bottom", fontsize=10)
    ax2.set_title("Revenue at Risk by Risk Tier")
    ax2.set_ylabel("Revenue")
    ax2.yaxis.set_major_formatter(mticker.FuncFormatter(_fmt_currency))
    ax2.grid(axis="y")

    fig.suptitle("Governance Risk Tier Overview", fontsize=14, fontweight="bold", y=1.02)
    _save(fig, "07_risk_tier_breakdown.png")


# ===========================================================================
# CHART 8 — Governance Priority Score Distribution
# ===========================================================================
def chart_priority_score_dist(customer_risk: pd.DataFrame) -> None:
    scores = customer_risk["governance_priority_score"]
    tier_colors = {
        "Critical": RISK,
        "High":     WARN,
        "Medium":   "#c8a800",
        "Low":      OK,
    }

    fig, ax = plt.subplots(figsize=(8, 4.5))
    n, bins, patches = ax.hist(scores, bins=25, color=INK, alpha=0.8, edgecolor=PAPER, linewidth=0.4)

    for patch, left_edge in zip(patches, bins[:-1]):
        if left_edge >= 80:
            patch.set_facecolor(RISK)
        elif left_edge >= 65:
            patch.set_facecolor(WARN)
        elif left_edge >= 45:
            patch.set_facecolor("#c8a800")
        else:
            patch.set_facecolor(OK)

    for score, label, ypos in [(45, "Medium", 0.88), (65, "High", 0.88), (80, "Critical", 0.88)]:
        ax.axvline(score, color=INK_LIGHT, lw=1, ls=":")
        ax.text(score + 0.5, ax.get_ylim()[1] * ypos, label,
                fontsize=8, color=INK_LIGHT, va="top")

    ax.set_title("Governance Priority Score Distribution")
    ax.set_xlabel("Governance Priority Score (0–100)")
    ax.set_ylabel("Customers")
    ax.grid(axis="y")

    _save(fig, "08_governance_score_distribution.png")


# ===========================================================================
# CHART 9 — Top 20 Customers by Governance Priority Score
# ===========================================================================
def chart_top_customers(customer_risk: pd.DataFrame) -> None:
    tier_colors = {
        "Critical": RISK,
        "High":     WARN,
        "Medium":   "#c8a800",
        "Low":      OK,
    }
    top = customer_risk.nlargest(20, "governance_priority_score").sort_values("governance_priority_score")
    colors = [tier_colors.get(t, INFO) for t in top["risk_tier"]]

    fig, ax = plt.subplots(figsize=(9, 7))
    bars = ax.barh(range(len(top)), top["governance_priority_score"], color=colors, edgecolor=PAPER, linewidth=0.3)

    ax.set_yticks(range(len(top)))
    ax.set_yticklabels([f"Customer {cid}" for cid in top["customer_id"]], fontsize=8)
    ax.set_xlabel("Governance Priority Score")
    ax.set_title("Top 20 Customers by Governance Priority Score")
    ax.grid(axis="x")

    for i, (score, tier, action) in enumerate(
        zip(top["governance_priority_score"], top["risk_tier"], top["recommended_action"])
    ):
        ax.text(score + 0.3, i, f" {score:.1f}  |  {tier}", va="center", fontsize=7.5, color=INK_LIGHT)

    from matplotlib.patches import Patch
    legend_elements = [Patch(facecolor=c, label=t) for t, c in tier_colors.items()]
    ax.legend(handles=legend_elements, loc="lower right", framealpha=0.85, fontsize=8)

    _save(fig, "09_top20_customers_priority.png")


# ===========================================================================
# MAIN
# ===========================================================================
def main() -> None:
    print(f"\n{'='*60}")
    print(" Pricing Governance — Analytical Graphs")
    print(f"{'='*60}\n")

    data = build_data()

    print("\nGenerating charts…")
    chart_monthly_revenue(data["metrics"])
    chart_discount_distribution(data["metrics"])
    chart_revenue_by_bucket(data["metrics"])
    chart_margin_by_bucket(data["metrics"])
    chart_segment_health(data["segment_summary"])
    chart_channel_segment_heatmap(data["seg_channel"])
    chart_risk_tier(data["customer_risk"])
    chart_priority_score_dist(data["customer_risk"])
    chart_top_customers(data["customer_risk"])

    print(f"\n✓  All charts saved to outputs/Graphs/\n")

    print("Graph Index")
    print("-" * 60)
    index = [
        ("01_monthly_revenue_trend.png",        "Monthly total revenue + high-discount share overlay. Tracks business trajectory and whether discount dependency is growing over time."),
        ("02_discount_depth_distribution.png",   "Histogram of discount depth at order-item level. Shows concentration of discounts and the share exceeding the 20% policy threshold."),
        ("03_revenue_by_discount_bucket.png",    "Revenue split across 5 discount buckets. Quantifies how much top-line revenue carries heavy discount risk."),
        ("04_margin_by_discount_bucket.png",     "Box-plot of gross margin proxy per bucket. Visualises the margin cost of each discount tier vs the 45% healthy floor."),
        ("05_segment_pricing_health.png",        "Avg discount vs avg margin by customer segment. Flags segments with high discounts AND low margins requiring policy action."),
        ("06_channel_segment_discount_heatmap.png", "Discount heatmap across channel × segment combinations. Highlights specific channel/segment pairs that need rep-level investigation."),
        ("07_risk_tier_breakdown.png",           "Customer count and revenue split by risk tier (Critical / High / Medium / Low). Board-level governance overview."),
        ("08_governance_score_distribution.png", "Histogram of the composite governance priority score (0–100). Shows the shape of the risk population and tier boundaries."),
        ("09_top20_customers_priority.png",      "Horizontal bar chart of the 20 highest-priority customers. Actionable watchlist for the next pricing review cycle."),
    ]
    for fname, desc in index:
        print(f"  {fname}")
        print(f"    → {desc}\n")


if __name__ == "__main__":
    main()
