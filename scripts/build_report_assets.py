"""
Build the publication chart pack and report statistics.

Reads processed data only (data/processed/) and writes:
  - outputs/graphs/NN_*.png   (editorial chart pack, one chart per question)
  - data/processed/report_stats.json  (figures consumed by the PDF builder)

Run:
    python scripts/build_report_assets.py
"""
from __future__ import annotations

import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
PROC = ROOT / "data" / "processed"
MART = PROC / "sql_marts"
GRAPHS = ROOT / "outputs" / "graphs"
GRAPHS.mkdir(parents=True, exist_ok=True)
POLICY = json.loads((ROOT / "config" / "policy_thresholds.json").read_text(encoding="utf-8"))
HIGH_DISCOUNT_THRESHOLD = float(POLICY["high_discount_threshold"])
SENSITIVITY_THRESHOLDS = [float(value) for value in POLICY["high_discount_sensitivity_thresholds"]]

# ---------------------------------------------------------------------------
# Editorial design tokens (cohesive with the command-center dashboard)
# ---------------------------------------------------------------------------
PAPER = "#f4f1ea"
INK = "#1a1a1a"
INK_LIGHT = "#6b6b6b"
GRID = "#d8d4cc"
ACCENT = "#8c2920"   # oxblood — the single accent for emphasis
WARN = "#936323"     # amber — used only for the warning tier
OK = "#3c5d2e"       # forest — used only for the healthy tier
NEUTRAL = "#b7b1a6"  # muted clay for non-emphasised series
NEUTRAL_D = "#8a8478"

plt.rcParams.update({
    "figure.facecolor": PAPER,
    "axes.facecolor": PAPER,
    "savefig.facecolor": PAPER,
    "axes.edgecolor": INK,
    "axes.linewidth": 0.8,
    "axes.labelcolor": INK,
    "text.color": INK,
    "xtick.color": INK_LIGHT,
    "ytick.color": INK_LIGHT,
    "grid.color": GRID,
    "grid.linewidth": 0.6,
    "axes.grid": True,
    "axes.grid.axis": "y",
    "axes.spines.top": False,
    "axes.spines.right": False,
    "font.family": "DejaVu Sans",
    "axes.titlesize": 13,
    "axes.titleweight": "bold",
    "axes.labelsize": 10,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "legend.fontsize": 9,
    "figure.dpi": 160,
    "savefig.dpi": 160,
    "savefig.bbox": "tight",
})

SEG_ORDER = ["Enterprise", "Public Sector", "Mid-Market", "SMB"]
CHAN_ORDER = ["Reseller", "Partner", "Direct", "Online"]


def _save(fig, name: str):
    path = GRAPHS / name
    fig.savefig(path, facecolor=PAPER)
    plt.close(fig)
    print("wrote", path.relative_to(ROOT))


def _kicker(ax, kicker: str, title: str, subtitle: str | None = None):
    """Editorial heading: small caps kicker, bold title, light subtitle."""
    ax.set_title("")
    fig = ax.figure
    fig.text(0.012, 0.985, kicker.upper(), ha="left", va="top",
             fontsize=8.5, color=ACCENT, weight="bold", family="DejaVu Sans")
    fig.text(0.012, 0.94, title, ha="left", va="top", fontsize=14.5,
             color=INK, weight="bold")
    if subtitle:
        fig.text(0.012, 0.895, subtitle, ha="left", va="top", fontsize=9.5,
                 color=INK_LIGHT)


def _src(fig, text: str | None = None):
    text = text or f"Source: pricing governance pipeline, processed marts. {COVERAGE_LABEL}."
    fig.text(0.012, 0.012, text, ha="left", va="bottom", fontsize=7.2,
             color=NEUTRAL_D, style="italic")


def _pct(x, _=None):
    return f"{x*100:.0f}%"


def _money_m(x, _=None):
    return f"${x/1e6:,.0f}M"


# ---------------------------------------------------------------------------
# Load
# ---------------------------------------------------------------------------
oi = pd.read_csv(PROC / "order_item_pricing_metrics.csv")
monthly = pd.read_csv(MART / "mart_monthly_pricing_health.csv", parse_dates=["order_month"])
seg = pd.read_csv(PROC / "segment_pricing_summary.csv")
segchan = pd.read_csv(PROC / "segment_channel_diagnostics.csv")
prod = pd.read_csv(MART / "mart_product_pricing_summary.csv")
cust = pd.read_csv(PROC / "customer_risk_scores.csv")
prof = pd.read_csv(PROC / "customer_pricing_profile.csv")
risk_tier = pd.read_csv(PROC / "risk_tier_summary.csv")
driver = pd.read_csv(PROC / "main_driver_summary.csv")
# overall health from the warehouse mart (robust to outputs/ cleanup)
overall = pd.read_csv(MART / "mart_overall_pricing_health.csv").iloc[0]
COVERAGE_LABEL = (
    f"{monthly['order_month'].min():%B %Y} to {monthly['order_month'].max():%B %Y}"
)

# threshold sensitivity recomputed from the order-item grain, mirroring
# src/analysis/formal_analysis._build_threshold_sensitivity (self-contained,
# so the asset build does not depend on transient pipeline outputs)
_total_rev = oi["line_revenue"].sum()
_thr_rows = []
for _t in SENSITIVITY_THRESHOLDS:
    _mask = oi["discount_depth"] >= _t
    _hd_rev = oi.loc[_mask, "line_revenue"].sum()
    _thr_rows.append({
        "high_discount_threshold": _t,
        "high_discount_revenue_share": _hd_rev / _total_rev,
        "high_discount_order_item_share": float(_mask.mean()),
        "margin_proxy_pct_on_high_discount": (
            oi.loc[_mask, "gross_margin_value"].sum() / _hd_rev if _hd_rev > 0 else float("nan")),
        "revenue_with_margin_at_risk": float(
            oi.loc[_mask & (oi["margin_proxy_pct"] < 0.35), "line_revenue"].sum()),
    })
thr = pd.DataFrame(_thr_rows)

seg = seg.set_index("segment").reindex(SEG_ORDER).reset_index()

# ===========================================================================
# 01  Revenue trend with discount pressure overlay
# ===========================================================================
fig, ax = plt.subplots(figsize=(9.2, 5.0))
fig.subplots_adjust(top=0.80, bottom=0.13, left=0.085, right=0.91)
ax.bar(monthly["order_month"], monthly["revenue"], width=22, color=NEUTRAL, label="Monthly revenue")
ax.yaxis.set_major_formatter(mticker.FuncFormatter(_money_m))
ax.set_ylabel("Revenue")
ax.margins(x=0.01)
ax2 = ax.twinx()
ax2.grid(False)
ax2.plot(monthly["order_month"], monthly["weighted_discount_pct"], color=ACCENT, lw=2.2)
ax2.yaxis.set_major_formatter(mticker.FuncFormatter(_pct))
ax2.set_ylabel("Weighted discount", color=ACCENT)
ax2.tick_params(axis="y", colors=ACCENT)
ax2.set_ylim(0.10, 0.22)
ax2.spines["right"].set_visible(True)
ax2.spines["right"].set_color(ACCENT)
xlast = monthly["order_month"].iloc[-1]
ax2.annotate("Weighted discount", (xlast, monthly["weighted_discount_pct"].iloc[-1]),
             xytext=(-4, 10), textcoords="offset points", color=ACCENT, fontsize=9, weight="bold", ha="right")
_kicker(ax, "Trend", "Revenue held flat while discount pressure stayed elevated",
        f"Monthly billed revenue (bars) against the revenue-weighted realized discount (line), {COVERAGE_LABEL}")
_src(fig)
_save(fig, "01_revenue_trend_discount_overlay.png")

# ===========================================================================
# 02  Price realization erosion over time
# ===========================================================================
monthly["price_realization"] = monthly["revenue"] / monthly["list_revenue"]
fig, ax = plt.subplots(figsize=(9.2, 5.0))
fig.subplots_adjust(top=0.80, bottom=0.13, left=0.10, right=0.96)
ax.fill_between(monthly["order_month"], monthly["price_realization"], 1.0,
                color=ACCENT, alpha=0.10)
ax.plot(monthly["order_month"], monthly["price_realization"], color=ACCENT, lw=2.2)
ax.axhline(1.0, color=INK, lw=0.8)
mean_pr = monthly["price_realization"].mean()
ax.axhline(mean_pr, color=INK_LIGHT, lw=0.9, ls="--")
ax.annotate(f"{len(monthly)}-month mean {mean_pr*100:.1f}%", (monthly['order_month'].iloc[2], mean_pr),
            xytext=(0, 8), textcoords="offset points", color=INK_LIGHT, fontsize=8.5)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(_pct))
ax.set_ylim(0.78, 1.005)
ax.set_ylabel("Price realization (billed / list)")
ax.margins(x=0.01)
_kicker(ax, "Trend", "One in five list-price dollars is given away every month",
        "Share of list value actually billed. The shaded band is revenue forgone to discount")
_src(fig)
_save(fig, "02_price_realization_trend.png")

# ===========================================================================
# 03  Discount depth distribution
# ===========================================================================
fig, ax = plt.subplots(figsize=(9.2, 5.0))
fig.subplots_adjust(top=0.80, bottom=0.13, left=0.085, right=0.96)
d = oi["discount_pct"] * 100
ax.hist(d, bins=40, color=NEUTRAL, edgecolor=PAPER, linewidth=0.4)
med = d.median()
ax.axvline(med, color=ACCENT, lw=2)
high_discount_pct = HIGH_DISCOUNT_THRESHOLD * 100
ax.axvline(high_discount_pct, color=INK, lw=1.0, ls="--")
ax.annotate(f"Median {med:.1f}%", (med, ax.get_ylim()[1]*0.92), xytext=(8, 0),
            textcoords="offset points", color=ACCENT, fontsize=9.5, weight="bold")
ax.annotate(f"High-discount line ({high_discount_pct:.0f}%)", (high_discount_pct, ax.get_ylim()[1]*0.62), xytext=(8, 0),
            textcoords="offset points", color=INK, fontsize=8.8)
ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.0f}%"))
ax.set_xlabel("Line-item discount")
ax.set_ylabel("Order items")
_kicker(ax, "Distribution", "Discounting clusters in a tight 10-20% band, not at the edges",
        f"All {len(oi):,} order items by realized discount depth")
_src(fig)
_save(fig, "03_discount_depth_distribution.png")

# ===========================================================================
# 04  Revenue by discount bucket (composition)
# ===========================================================================
bucket_order = ["0-5%", "5-10%", "10-20%", "20-30%", "30%+"]
rev_b = oi.groupby("discount_bucket")["line_revenue"].sum().reindex(bucket_order).fillna(0)
fig, ax = plt.subplots(figsize=(9.2, 5.0))
fig.subplots_adjust(top=0.80, bottom=0.13, left=0.11, right=0.96)
colors = [NEUTRAL, NEUTRAL, NEUTRAL, ACCENT, ACCENT]
bars = ax.barh(bucket_order, rev_b.values, color=colors)
ax.invert_yaxis()
ax.xaxis.set_major_formatter(mticker.FuncFormatter(_money_m))
ax.grid(axis="x"); ax.grid(axis="y", visible=False)
tot = rev_b.sum()
for b, v in zip(bars, rev_b.values):
    ax.text(v + tot*0.01, b.get_y()+b.get_height()/2, f"${v/1e6:,.0f}M  ({v/tot*100:.0f}%)",
            va="center", fontsize=9, color=INK)
ax.set_xlim(0, tot*0.78)
ax.set_xlabel("Revenue")
_kicker(ax, "Composition", "Most revenue carries a 10-20% discount, but the deep tail is heavy",
        "Billed revenue by discount band. Bands above 20% are highlighted")
_src(fig)
_save(fig, "04_revenue_by_discount_bucket.png")

# ===========================================================================
# 05  Margin by discount bucket (variance)
# ===========================================================================
mb = oi.groupby("discount_bucket").apply(
    lambda g: pd.Series({"margin": g["gross_margin_value"].sum()/g["line_revenue"].sum()}),
    include_groups=False).reindex(bucket_order)
fig, ax = plt.subplots(figsize=(9.2, 5.0))
fig.subplots_adjust(top=0.80, bottom=0.13, left=0.09, right=0.96)
vals = mb["margin"].values * 100
colors = [OK if v == max(vals) else (ACCENT if v == min(vals) else NEUTRAL) for v in vals]
bars = ax.bar(bucket_order, vals, color=colors, width=0.62)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.0f}%"))
ax.set_ylabel("Gross margin proxy")
ax.set_xlabel("Discount band")
for b, v in zip(bars, vals):
    ax.text(b.get_x()+b.get_width()/2, v+0.4, f"{v:.1f}%", ha="center", fontsize=9.5, weight="bold")
ax.set_ylim(0, max(vals)*1.15)
_kicker(ax, "Variance", "Each step deeper into discount strips roughly four margin points",
        "Blended gross-margin proxy within each discount band")
_src(fig)
_save(fig, "05_margin_by_discount_bucket.png")

# ===========================================================================
# 06  Discount vs margin correlation (customer level)
# ===========================================================================
fig, ax = plt.subplots(figsize=(9.2, 5.2))
fig.subplots_adjust(top=0.80, bottom=0.12, left=0.09, right=0.96)
x = prof["avg_discount_pct"]*100
y = prof["avg_margin_proxy_pct"]*100
sizes = (prof["total_revenue"]/prof["total_revenue"].max())*420 + 6
ax.scatter(x, y, s=sizes, color=ACCENT, alpha=0.18, edgecolor="none")
coef = np.polyfit(x, y, 1)
xs = np.linspace(x.min(), x.max(), 50)
ax.plot(xs, np.polyval(coef, xs), color=INK, lw=1.8, ls="--")
r = np.corrcoef(x, y)[0, 1]
ax.annotate(f"r = {r:.2f}\nslope {coef[0]:.2f} margin pts per discount pt",
            (0.97, 0.95), xycoords="axes fraction", ha="right", va="top",
            fontsize=9.5, color=INK, weight="bold")
ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
ax.set_xlabel("Customer average discount")
ax.set_ylabel("Customer average margin proxy")
_kicker(ax, "Correlation", "Deeper discounting reliably tracks thinner margin",
        f"Each bubble is one of {len(prof):,} customers, sized by revenue")
_src(fig)
_save(fig, "06_discount_margin_correlation.png")

# ===========================================================================
# 07  Segment pricing health (discount vs margin, bubble = revenue)
# ===========================================================================
fig, ax = plt.subplots(figsize=(9.2, 5.4))
fig.subplots_adjust(top=0.80, bottom=0.12, left=0.09, right=0.96)
sx = seg["avg_discount_pct"]*100
sy = seg["avg_margin_proxy_pct"]*100
ss = (seg["total_revenue"]/seg["total_revenue"].max())*2600 + 200
seg_colors = [ACCENT, WARN, NEUTRAL_D, OK]
ax.scatter(sx, sy, s=ss, color=seg_colors, alpha=0.85, edgecolor=PAPER, linewidth=1.5, zorder=3)
for i, row in seg.iterrows():
    ax.annotate(f"{row['segment']}\n${row['total_revenue']/1e6:,.0f}M  ·  high-disc {row['share_high_discount']*100:.0f}%",
                (sx[i], sy[i]), xytext=(0, -38 if row['segment']=='Enterprise' else 16),
                textcoords="offset points", ha="center", fontsize=8.6, color=INK)
ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda v, _: f"{v:.0f}%"))
ax.set_xlabel("Average discount")
ax.set_ylabel("Average margin proxy")
ax.set_xlim(9, 23)
ax.set_ylim(40, 55)
_kicker(ax, "Risk", "Enterprise carries the most revenue at the worst discount-margin position",
        "Segment position by discount and margin. Bubble area is total revenue")
_src(fig)
_save(fig, "07_segment_pricing_health.png")

# ===========================================================================
# 08  Segment x channel discount heatmap (concentration)
# ===========================================================================
piv = segchan.pivot(index="segment", columns="sales_channel", values="avg_discount_pct")
piv = piv.reindex(index=SEG_ORDER, columns=CHAN_ORDER) * 100
fig, ax = plt.subplots(figsize=(8.6, 5.2))
fig.subplots_adjust(top=0.78, bottom=0.10, left=0.16, right=0.99)
from matplotlib.colors import LinearSegmentedColormap
cmap = LinearSegmentedColormap.from_list("oxblood", [PAPER, "#d8b6ad", ACCENT])
im = ax.imshow(piv.values, cmap=cmap, aspect="auto", vmin=10, vmax=24)
ax.set_xticks(range(len(CHAN_ORDER))); ax.set_xticklabels(CHAN_ORDER)
ax.set_yticks(range(len(SEG_ORDER))); ax.set_yticklabels(SEG_ORDER)
ax.grid(False)
for i in range(piv.shape[0]):
    for j in range(piv.shape[1]):
        v = piv.values[i, j]
        ax.text(j, i, f"{v:.1f}%", ha="center", va="center",
                color=PAPER if v > 18 else INK, fontsize=9.5, weight="bold")
_kicker(ax, "Concentration", "Discounting concentrates where Enterprise meets the reseller channel",
        "Average discount by segment and sales channel. Darker is deeper")
_src(fig)
_save(fig, "08_segment_channel_heatmap.png")

# ===========================================================================
# 09  Channel discount ladder (ranking)
# ===========================================================================
chan = oi.groupby("sales_channel").apply(
    lambda g: pd.Series({
        "discount": (g["line_list_revenue"].sum()-g["line_revenue"].sum())/g["line_list_revenue"].sum(),
        "revenue": g["line_revenue"].sum(),
    }), include_groups=False).reindex(CHAN_ORDER)
fig, ax = plt.subplots(figsize=(9.2, 5.0))
fig.subplots_adjust(top=0.80, bottom=0.13, left=0.10, right=0.96)
vals = chan["discount"].values*100
colors = [ACCENT if v == max(vals) else NEUTRAL for v in vals]
bars = ax.bar(CHAN_ORDER, vals, color=colors, width=0.6)
for b, v, rv in zip(bars, vals, chan["revenue"].values):
    ax.text(b.get_x()+b.get_width()/2, v+0.25, f"{v:.1f}%", ha="center", fontsize=9.5, weight="bold")
    ax.text(b.get_x()+b.get_width()/2, 0.6, f"${rv/1e6:,.0f}M", ha="center", fontsize=8.2, color=PAPER, weight="bold")
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.0f}%"))
ax.set_ylabel("Weighted discount")
ax.set_ylim(0, max(vals)*1.16)
_kicker(ax, "Ranking", "Indirect channels discount nearly twice as deep as Online",
        "Revenue-weighted discount by channel. Revenue in white at base")
_src(fig)
_save(fig, "09_channel_discount_ladder.png")

# ===========================================================================
# 10  Region comparison (geography)
# ===========================================================================
reg = oi.groupby("region").apply(
    lambda g: pd.Series({
        "discount": (g["line_list_revenue"].sum()-g["line_revenue"].sum())/g["line_list_revenue"].sum(),
        "margin": g["gross_margin_value"].sum()/g["line_revenue"].sum(),
        "revenue": g["line_revenue"].sum(),
    }), include_groups=False).sort_values("discount", ascending=False)
fig, ax = plt.subplots(figsize=(9.2, 5.0))
fig.subplots_adjust(top=0.80, bottom=0.13, left=0.10, right=0.90)
yp = np.arange(len(reg))
ax.barh(yp, reg["discount"].values*100, color=NEUTRAL, height=0.6)
ax.set_yticks(yp); ax.set_yticklabels(reg.index)
ax.invert_yaxis()
ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.0f}%"))
ax.grid(axis="x"); ax.grid(axis="y", visible=False)
for i, (disc, rv) in enumerate(zip(reg["discount"].values, reg["revenue"].values)):
    ax.text(disc*100+0.15, i, f"{disc*100:.1f}%  ·  ${rv/1e6:,.0f}M", va="center", fontsize=9, color=INK)
ax.set_xlim(0, reg["discount"].max()*100*1.35)
ax.set_xlabel("Weighted discount")
_kicker(ax, "Geography", "Discount depth is roughly even across regions",
        "Weighted discount and revenue by customer region")
_src(fig)
_save(fig, "10_region_comparison.png")

# ===========================================================================
# 11  Product category margin vs discount (composition)
# ===========================================================================
cat = oi.groupby("category").apply(
    lambda g: pd.Series({
        "discount": (g["line_list_revenue"].sum()-g["line_revenue"].sum())/g["line_list_revenue"].sum(),
        "margin": g["gross_margin_value"].sum()/g["line_revenue"].sum(),
        "revenue": g["line_revenue"].sum(),
    }), include_groups=False).sort_values("revenue", ascending=True)
fig, ax = plt.subplots(figsize=(9.2, 5.2))
fig.subplots_adjust(top=0.80, bottom=0.13, left=0.16, right=0.92)
yp = np.arange(len(cat))
ax.barh(yp-0.2, cat["discount"].values*100, height=0.38, color=ACCENT, label="Discount")
ax.barh(yp+0.2, cat["margin"].values*100, height=0.38, color=NEUTRAL_D, label="Margin proxy")
ax.set_yticks(yp); ax.set_yticklabels(cat.index)
ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.0f}%"))
ax.grid(axis="x"); ax.grid(axis="y", visible=False)
ax.legend(loc="lower right", frameon=False)
for i, (d, m) in enumerate(zip(cat["discount"].values, cat["margin"].values)):
    ax.text(d*100+0.4, i-0.2, f"{d*100:.0f}%", va="center", fontsize=8.4, color=ACCENT)
    ax.text(m*100+0.4, i+0.2, f"{m*100:.0f}%", va="center", fontsize=8.4, color=NEUTRAL_D)
ax.set_xlim(0, 60)
_kicker(ax, "Composition", "Professional Services earns the thinnest margin on an ordinary discount",
        "Discount versus margin proxy by product category")
_src(fig)
_save(fig, "11_category_margin_vs_discount.png")

# ===========================================================================
# 12  Top products by revenue with discount marker (ranking)
# ===========================================================================
top_prod = prod.sort_values("revenue", ascending=False).head(12).iloc[::-1]
fig, ax = plt.subplots(figsize=(9.2, 5.6))
fig.subplots_adjust(top=0.80, bottom=0.11, left=0.30, right=0.91)
yp = np.arange(len(top_prod))
bars = ax.barh(yp, top_prod["revenue"].values, color=NEUTRAL, height=0.66)
ax.set_yticks(yp); ax.set_yticklabels(top_prod["product_name"], fontsize=8.6)
ax.xaxis.set_major_formatter(mticker.FuncFormatter(_money_m))
ax.grid(axis="x"); ax.grid(axis="y", visible=False)
hi = top_prod["high_discount_share"].values
for b, v, h in zip(bars, top_prod["revenue"].values, hi):
    if h >= 0.30:
        b.set_color(ACCENT)
    ax.text(v + top_prod['revenue'].max()*0.01, b.get_y()+b.get_height()/2,
            f"${v/1e6:,.0f}M  ·  {h*100:.0f}% deep", va="center", fontsize=8.2, color=INK)
ax.set_xlim(0, top_prod["revenue"].max()*1.22)
ax.set_xlabel("Revenue")
_kicker(ax, "Ranking", "The top-revenue product also carries the deepest discount exposure",
        "Top 12 products by revenue. Red marks any product with 30%+ of revenue deeply discounted")
_src(fig)
_save(fig, "12_top_products_revenue.png")

# ===========================================================================
# 13  Risk tier breakdown (customers vs revenue)
# ===========================================================================
rt = risk_tier.set_index("risk_tier").reindex(["High", "Medium", "Low"])
fig, axes = plt.subplots(1, 2, figsize=(9.4, 5.0))
fig.subplots_adjust(top=0.78, bottom=0.12, left=0.09, right=0.97, wspace=0.32)
tcolors = [ACCENT, WARN, OK]
axes[0].bar(rt.index, rt["customers"], color=tcolors, width=0.62)
axes[0].set_ylabel("Customers")
for i, v in enumerate(rt["customers"]):
    axes[0].text(i, v+12, f"{int(v)}", ha="center", fontsize=9.5, weight="bold")
axes[0].set_title("By customer count", fontsize=10.5, weight="bold", color=INK_LIGHT)
axes[1].bar(rt.index, rt["total_revenue"]/1e6, color=tcolors, width=0.62)
axes[1].yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}M"))
axes[1].set_ylabel("Revenue")
for i, v in enumerate(rt["total_revenue"]/1e6):
    axes[1].text(i, v+18, f"${v:,.0f}M", ha="center", fontsize=9.5, weight="bold")
axes[1].set_title("By revenue exposed", fontsize=10.5, weight="bold", color=INK_LIGHT)
_kicker(axes[0], "Risk", "A small high-risk group sits on outsized revenue",
        "Customers and revenue by governance risk tier")
# _kicker clears the axes title, so re-apply the panel labels afterwards
axes[0].set_title("By customer count", fontsize=10.5, weight="bold", color=INK_LIGHT)
axes[1].set_title("By revenue exposed", fontsize=10.5, weight="bold", color=INK_LIGHT)
_src(fig)
_save(fig, "13_risk_tier_breakdown.png")

# ===========================================================================
# 14  Governance priority score distribution
# ===========================================================================
fig, ax = plt.subplots(figsize=(9.2, 5.0))
fig.subplots_adjust(top=0.80, bottom=0.13, left=0.08, right=0.96)
s = cust["governance_priority_score"]
ax.hist(s, bins=40, color=NEUTRAL, edgecolor=PAPER, linewidth=0.4)
p90 = s.quantile(0.90)
ax.axvline(p90, color=ACCENT, lw=2)
ax.annotate(f"90th percentile = {p90:.0f}\n{(s>=p90).sum()} customers above",
            (p90, ax.get_ylim()[1]*0.85), xytext=(10, 0), textcoords="offset points",
            color=ACCENT, fontsize=9.2, weight="bold")
ax.set_xlabel("Governance priority score (0-100)")
ax.set_ylabel("Customers")
_kicker(ax, "Distribution", "Priority is concentrated in a thin upper tail",
        f"Governance priority score across {len(cust):,} customers")
_src(fig)
_save(fig, "14_priority_score_distribution.png")

# ===========================================================================
# 15  Revenue concentration (Lorenz curve)
# ===========================================================================
rev_sorted = np.sort(prof["total_revenue"].values)[::-1]
cum = np.cumsum(rev_sorted)/rev_sorted.sum()
xfrac = np.arange(1, len(cum)+1)/len(cum)
fig, ax = plt.subplots(figsize=(9.2, 5.2))
fig.subplots_adjust(top=0.80, bottom=0.13, left=0.10, right=0.96)
ax.plot(xfrac*100, cum*100, color=ACCENT, lw=2.4)
ax.plot([0, 100], [0, 100], color=INK_LIGHT, lw=0.9, ls="--")
for q in (0.10, 0.20):
    idx = int(q*len(cum))-1
    ax.scatter([q*100], [cum[idx]*100], color=INK, zorder=5, s=28)
    ax.annotate(f"top {int(q*100)}% of customers = {cum[idx]*100:.0f}% of revenue",
                (q*100, cum[idx]*100), xytext=(12, -4), textcoords="offset points",
                fontsize=9, color=INK, weight="bold")
ax.set_xlabel("Cumulative share of customers (ranked by revenue)")
ax.set_ylabel("Cumulative share of revenue")
ax.set_xlim(0, 100); ax.set_ylim(0, 101)
_kicker(ax, "Concentration", "Revenue is highly concentrated, which makes targeted remediation viable",
        "Lorenz curve of revenue across the customer base")
_src(fig)
_save(fig, "15_revenue_concentration_lorenz.png")

# ===========================================================================
# 16  Threshold sensitivity (revenue at risk vs threshold)
# ===========================================================================
fig, ax = plt.subplots(figsize=(9.2, 5.0))
fig.subplots_adjust(top=0.80, bottom=0.13, left=0.11, right=0.90)
xt = thr["high_discount_threshold"]*100
ax.bar(xt, thr["revenue_with_margin_at_risk"]/1e6, width=2.4, color=NEUTRAL)
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}M"))
ax.set_ylabel("Revenue with margin at risk", color=INK)
ax.set_xlabel("High-discount threshold")
ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.0f}%"))
for x, v in zip(xt, thr["revenue_with_margin_at_risk"]/1e6):
    ax.text(x, v+2, f"${v:,.0f}M", ha="center", fontsize=9, weight="bold")
ax2 = ax.twinx(); ax2.grid(False)
ax2.plot(xt, thr["high_discount_revenue_share"]*100, color=ACCENT, lw=2.2, marker="o")
ax2.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.0f}%"))
ax2.set_ylabel("High-discount revenue share", color=ACCENT)
ax2.tick_params(axis="y", colors=ACCENT)
ax2.spines["right"].set_visible(True); ax2.spines["right"].set_color(ACCENT)
ax.set_xticks([15, 20, 25])
_kicker(ax, "Sensitivity", "The risk verdict is robust across plausible thresholds",
        "Revenue at risk (bars) and high-discount share (line) as the threshold moves")
_src(fig)
_save(fig, "16_threshold_sensitivity.png")

# ===========================================================================
# 17  Main risk driver composition
# ===========================================================================
dv = driver.set_index("main_risk_driver")
label_map = {
    "discount_dependency_score": "Discount dependency",
    "pricing_risk_score": "Pricing risk",
    "margin_erosion_score": "Margin erosion",
}
dv = dv.reindex(["discount_dependency_score", "pricing_risk_score", "margin_erosion_score"])
fig, ax = plt.subplots(figsize=(9.2, 5.0))
fig.subplots_adjust(top=0.80, bottom=0.13, left=0.10, right=0.93)
yp = np.arange(len(dv))
colors = [ACCENT, NEUTRAL, WARN]
bars = ax.barh(yp, dv["total_revenue"].values/1e6, color=colors, height=0.6)
ax.set_yticks(yp); ax.set_yticklabels([label_map[i] for i in dv.index])
ax.invert_yaxis()
ax.xaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"${x:,.0f}M"))
ax.grid(axis="x"); ax.grid(axis="y", visible=False)
for b, rv, c in zip(bars, dv["total_revenue"].values/1e6, dv["customers"].values):
    ax.text(rv + dv['total_revenue'].max()/1e6*0.01, b.get_y()+b.get_height()/2,
            f"${rv:,.0f}M  ·  {int(c)} customers", va="center", fontsize=9, color=INK)
ax.set_xlim(0, dv["total_revenue"].max()/1e6*1.25)
ax.set_xlabel("Revenue attributed to driver")
_kicker(ax, "Diagnosis", "Discount dependency is the dominant driver by revenue",
        "Primary risk driver assigned to each customer, aggregated by revenue")
_src(fig)
_save(fig, "17_main_risk_driver.png")

# ===========================================================================
# 18  Tenure cohort: discount behaviour by customer tenure
# ===========================================================================
prof2 = prof.copy()
# tenure proxy from order item table (days_since_signup at sale); aggregate per customer mean
ten = oi.groupby("customer_id")["days_since_signup"].mean()
prof2 = prof2.merge(ten.rename("tenure"), left_on="customer_id", right_index=True, how="left")
bins = [0, 365, 730, 1095, 1460, 99999]
labels = ["<1y", "1-2y", "2-3y", "3-4y", "4y+"]
prof2["tenure_band"] = pd.cut(prof2["tenure"], bins=bins, labels=labels)
coh = prof2.groupby("tenure_band", observed=True).agg(
    discount=("avg_discount_pct", "mean"),
    margin=("avg_margin_proxy_pct", "mean"),
    customers=("customer_id", "count")).reindex(labels)
fig, ax = plt.subplots(figsize=(9.2, 5.0))
fig.subplots_adjust(top=0.80, bottom=0.13, left=0.09, right=0.91)
ax.plot(labels, coh["discount"]*100, color=ACCENT, lw=2.2, marker="o", label="Avg discount")
ax.plot(labels, coh["margin"]*100, color=NEUTRAL_D, lw=2.0, marker="s", ls="--", label="Avg margin proxy")
ax.yaxis.set_major_formatter(mticker.FuncFormatter(lambda x, _: f"{x:.0f}%"))
ax.set_xlabel("Customer tenure at time of sale")
ax.set_ylabel("Rate")
ax.legend(loc="center right", frameon=False)
for i, (d, m) in enumerate(zip(coh["discount"]*100, coh["margin"]*100)):
    ax.annotate(f"{d:.1f}%", (i, d), xytext=(0, 8), textcoords="offset points", ha="center", fontsize=8.4, color=ACCENT)
_kicker(ax, "Cohort", "Discount depth is flat across tenure, so it is structural not promotional",
        "Average discount and margin proxy by customer tenure band")
_src(fig)
_save(fig, "18_tenure_cohort.png")

# ---------------------------------------------------------------------------
# Report statistics
# ---------------------------------------------------------------------------
top10_rev_share = float(cum[int(0.10*len(cum))-1])
top20_rev_share = float(cum[int(0.20*len(cum))-1])
revenue_forgone = float(overall["total_list_revenue"] - overall["total_revenue"])

oi["order_year"] = pd.to_datetime(oi["order_date"]).dt.year
oi["revenue_forgone"] = oi["line_list_revenue"] - oi["line_revenue"]
oi["high_discount_revenue"] = np.where(oi["high_discount_flag"].astype(bool), oi["line_revenue"], 0.0)
annual = (
    oi.groupby("order_year", as_index=False)
    .agg(
        revenue=("line_revenue", "sum"),
        list_revenue=("line_list_revenue", "sum"),
        revenue_forgone=("revenue_forgone", "sum"),
        gross_margin_value=("gross_margin_value", "sum"),
        high_discount_revenue=("high_discount_revenue", "sum"),
        order_items=("order_item_id", "count"),
    )
    .sort_values("order_year")
)
annual["price_realization"] = annual["revenue"] / annual["list_revenue"]
annual["weighted_discount_pct"] = 1 - annual["price_realization"]
annual["margin_proxy_pct"] = annual["gross_margin_value"] / annual["revenue"]
annual["high_discount_revenue_share"] = annual["high_discount_revenue"] / annual["revenue"]

segment_value = (
    oi.groupby("segment", as_index=False)
    .agg(
        revenue=("line_revenue", "sum"),
        list_revenue=("line_list_revenue", "sum"),
        revenue_forgone=("revenue_forgone", "sum"),
        gross_margin_value=("gross_margin_value", "sum"),
        high_discount_revenue=("high_discount_revenue", "sum"),
        order_items=("order_item_id", "count"),
        customers=("customer_id", "nunique"),
    )
)
segment_value["price_realization"] = segment_value["revenue"] / segment_value["list_revenue"]
segment_value["weighted_discount_pct"] = 1 - segment_value["price_realization"]
segment_value["margin_proxy_pct"] = segment_value["gross_margin_value"] / segment_value["revenue"]
segment_value["share_of_revenue_forgone"] = segment_value["revenue_forgone"] / revenue_forgone
segment_value["high_discount_revenue_share"] = segment_value["high_discount_revenue"] / segment_value["revenue"]
segment_value = segment_value.set_index("segment").reindex(SEG_ORDER).reset_index()

channel_value = (
    oi.groupby("sales_channel", as_index=False)
    .agg(
        revenue=("line_revenue", "sum"),
        list_revenue=("line_list_revenue", "sum"),
        revenue_forgone=("revenue_forgone", "sum"),
        gross_margin_value=("gross_margin_value", "sum"),
        high_discount_revenue=("high_discount_revenue", "sum"),
        order_items=("order_item_id", "count"),
        customers=("customer_id", "nunique"),
    )
)
channel_value["price_realization"] = channel_value["revenue"] / channel_value["list_revenue"]
channel_value["weighted_discount_pct"] = 1 - channel_value["price_realization"]
channel_value["margin_proxy_pct"] = channel_value["gross_margin_value"] / channel_value["revenue"]
channel_value["share_of_revenue_forgone"] = channel_value["revenue_forgone"] / revenue_forgone
channel_value["high_discount_revenue_share"] = channel_value["high_discount_revenue"] / channel_value["revenue"]
channel_value = channel_value.set_index("sales_channel").reindex(CHAN_ORDER).reset_index()

risk_detail = (
    cust.groupby("risk_tier", as_index=False)
    .agg(
        customers=("customer_id", "count"),
        revenue=("total_revenue", "sum"),
        avg_discount_pct=("avg_discount_pct", "mean"),
        avg_margin_proxy_pct=("avg_margin_proxy_pct", "mean"),
        revenue_high_discount_share=("revenue_high_discount_share", "mean"),
        avg_priority=("governance_priority_score", "mean"),
    )
)
risk_detail["revenue_share"] = risk_detail["revenue"] / float(cust["total_revenue"].sum())

er_mask = (segchan["segment"] == "Enterprise") & (segchan["sales_channel"] == "Reseller")
enterprise_reseller = segchan.loc[er_mask].iloc[0].to_dict()

recovery_scenarios = [
    {
        "realization_improvement_pp": points,
        "annualized_revenue_capture": float(overall["total_list_revenue"] * (points / 100)),
        "new_price_realization": float(overall["price_realization"] + (points / 100)),
    }
    for points in (1, 2, 3)
]

stats = {
    "n_order_items": int(len(oi)),
    "n_customers": int(len(prof)),
    "n_products": int(prod.shape[0]),
    "n_segments": int(seg["segment"].nunique()),
    "n_channels": int(segchan["sales_channel"].nunique()),
    "n_regions": int(oi["region"].nunique()),
    "n_categories": int(oi["category"].nunique()),
    "coverage": COVERAGE_LABEL,
    "n_months": int(monthly.shape[0]),
    "high_discount_threshold": HIGH_DISCOUNT_THRESHOLD,
    "high_discount_sensitivity_thresholds": SENSITIVITY_THRESHOLDS,
    "total_revenue": float(overall["total_revenue"]),
    "total_list_revenue": float(overall["total_list_revenue"]),
    "revenue_forgone": revenue_forgone,
    "margin_value": float(overall["total_margin_proxy_value"]),
    "avg_discount": float(overall["avg_realized_discount"]),
    "weighted_discount": float(overall["weighted_realized_discount"]),
    "high_discount_rev_share": float(overall["high_discount_revenue_share"]),
    "price_realization": float(overall["price_realization"]),
    "margin_proxy": float(overall["margin_proxy_pct"]),
    "pr_min": float(monthly["price_realization"].min()),
    "pr_max": float(monthly["price_realization"].max()),
    "pr_mean": float(monthly["price_realization"].mean()),
    "disc_margin_r": float(np.corrcoef(prof["avg_discount_pct"], prof["avg_margin_proxy_pct"])[0, 1]),
    "disc_margin_slope": float(np.polyfit(prof["avg_discount_pct"]*100, prof["avg_margin_proxy_pct"]*100, 1)[0]),
    "top10_rev_share": top10_rev_share,
    "top20_rev_share": top20_rev_share,
    "top10_customer_count": int(max(1, round(0.10 * len(prof)))),
    "top20_customer_count": int(max(1, round(0.20 * len(prof)))),
    "annual_summary": annual.to_dict(orient="records"),
    "segment_value_pool": segment_value.to_dict(orient="records"),
    "channel_value_pool": channel_value.to_dict(orient="records"),
    "risk_tier_detail": risk_detail.to_dict(orient="records"),
    "recovery_scenarios": recovery_scenarios,
    "segments": seg.to_dict(orient="records"),
    "risk_tiers": risk_tier.to_dict(orient="records"),
    "drivers": driver.to_dict(orient="records"),
    "threshold": thr.to_dict(orient="records"),
    "margin_best_bucket": float(mb["margin"].max()*100),
    "margin_worst_bucket": float(mb["margin"].min()*100),
    "channel": {k: {"discount": float(chan.loc[k, "discount"]), "revenue": float(chan.loc[k, "revenue"])} for k in CHAN_ORDER},
    "category": cat.reset_index().to_dict(orient="records"),
    "region": reg.reset_index().to_dict(orient="records"),
    "high_tier_customers": int(rt.loc["High", "customers"]),
    "high_tier_revenue": float(rt.loc["High", "total_revenue"]),
    "p90_priority": float(s.quantile(0.90)),
    "enterprise_reseller_disc": float(segchan[(segchan.segment=="Enterprise")&(segchan.sales_channel=="Reseller")]["avg_discount_pct"].iloc[0]),
    "enterprise_reseller": {
        "revenue": float(enterprise_reseller["revenue"]),
        "avg_discount_pct": float(enterprise_reseller["avg_discount_pct"]),
        "high_discount_share": float(enterprise_reseller["high_discount_share"]),
        "order_item_count": int(enterprise_reseller["order_item_count"]),
        "avg_margin_proxy_pct": float(enterprise_reseller["avg_margin_proxy_pct"]),
    },
}
(PROC / "report_stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
print("\nwrote data/processed/report_stats.json")
print("charts:", len(list(GRAPHS.glob('*.png'))))
