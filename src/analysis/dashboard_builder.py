from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path
from typing import Dict

import numpy as np
import pandas as pd

ALL_VALUE = "All"


def _as_records(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.to_json(orient="records", date_format="iso"))


def _round_numeric_columns(df: pd.DataFrame, precision_map: dict[str, int]) -> pd.DataFrame:
    out = df.copy()
    for col, precision in precision_map.items():
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").round(precision)
    return out


def _safe_ratio(numerator: pd.Series, denominator: pd.Series) -> pd.Series:
    return np.where(denominator > 0, numerator / denominator, 0.0)


def _build_kpi_cube(pricing: pd.DataFrame, dims: list[str]) -> pd.DataFrame:
    metric_cols = [
        "line_revenue",
        "line_list_revenue",
        "discount_weighted_num",
        "high_discount_revenue",
        "margin_risk_revenue",
    ]
    working = pricing[[*dims, *metric_cols]].copy()

    parts: list[pd.DataFrame] = []
    for size in range(len(dims) + 1):
        for subset in combinations(dims, size):
            group_cols = list(subset)
            if group_cols:
                agg = (
                    working.groupby(group_cols, as_index=False)
                    .agg(
                        net_revenue=("line_revenue", "sum"),
                        list_revenue=("line_list_revenue", "sum"),
                        discount_weighted_num=("discount_weighted_num", "sum"),
                        high_discount_revenue=("high_discount_revenue", "sum"),
                        margin_at_risk=("margin_risk_revenue", "sum"),
                    )
                )
            else:
                agg = pd.DataFrame(
                    [
                        {
                            "net_revenue": float(working["line_revenue"].sum()),
                            "list_revenue": float(working["line_list_revenue"].sum()),
                            "discount_weighted_num": float(working["discount_weighted_num"].sum()),
                            "high_discount_revenue": float(working["high_discount_revenue"].sum()),
                            "margin_at_risk": float(working["margin_risk_revenue"].sum()),
                        }
                    ]
                )

            for dim in dims:
                if dim not in agg.columns:
                    agg[dim] = ALL_VALUE

            agg["weighted_discount_pct"] = _safe_ratio(agg["discount_weighted_num"], agg["list_revenue"])
            agg["high_discount_revenue_share"] = _safe_ratio(agg["high_discount_revenue"], agg["net_revenue"])
            agg["margin_at_risk_share"] = _safe_ratio(agg["margin_at_risk"], agg["net_revenue"])

            parts.append(
                agg[
                    [
                        *dims,
                        "net_revenue",
                        "weighted_discount_pct",
                        "high_discount_revenue_share",
                        "margin_at_risk",
                        "margin_at_risk_share",
                    ]
                ]
            )

    cube = pd.concat(parts, ignore_index=True)
    cube = cube.drop_duplicates(subset=dims)
    return cube.sort_values(dims).reset_index(drop=True)


def _build_monthly_pricing_agg(pricing: pd.DataFrame, dims: list[str]) -> pd.DataFrame:
    agg = (
        pricing.groupby(["order_month", *dims], as_index=False)
        .agg(
            line_revenue=("line_revenue", "sum"),
            line_list_revenue=("line_list_revenue", "sum"),
            discount_weighted_num=("discount_weighted_num", "sum"),
            high_discount_revenue=("high_discount_revenue", "sum"),
            margin_risk_revenue=("margin_risk_revenue", "sum"),
        )
        .sort_values(["order_month", *dims])
    )
    return agg.reset_index(drop=True)


def _build_customer_pricing_rows(pricing: pd.DataFrame, selected_customers: set[str]) -> pd.DataFrame:
    filtered = pricing[pricing["customer_id"].isin(selected_customers)]
    return (
        filtered.groupby(
            ["order_month", "customer_id", "segment", "region", "category", "sales_channel"],
            as_index=False,
        )
        .agg(
            filtered_revenue=("line_revenue", "sum"),
            filtered_list_revenue=("line_list_revenue", "sum"),
            filtered_discount_num=("discount_weighted_num", "sum"),
        )
        .sort_values(["order_month", "customer_id", "category", "sales_channel"])
        .reset_index(drop=True)
    )


def build_executive_dashboard(
    processed_tables: Dict[str, pd.DataFrame],
    dashboard_dir: Path,
) -> Path:
    dashboard_dir.mkdir(parents=True, exist_ok=True)

    pricing = processed_tables["order_item_pricing_metrics"].copy()
    risk = processed_tables["customer_risk_scores"].copy()

    pricing["order_date"] = pd.to_datetime(pricing["order_date"])
    pricing["order_month"] = pd.to_datetime(pricing["order_month"]).dt.strftime("%Y-%m")
    pricing["discount_weighted_num"] = pricing["discount_depth"] * pricing["line_list_revenue"]
    pricing["high_discount_revenue"] = np.where(pricing["high_discount_flag"] == 1, pricing["line_revenue"], 0.0)
    pricing["margin_risk_revenue"] = np.where(
        (pricing["high_discount_flag"] == 1) & (pricing["margin_proxy_pct"] < 0.35),
        pricing["line_revenue"],
        0.0,
    )

    dims = ["segment", "region", "category", "sales_channel"]
    kpi_cube = _build_kpi_cube(pricing, dims=dims)
    monthly_agg = _build_monthly_pricing_agg(pricing, dims=dims)

    risk_export = risk[
        [
            "customer_id",
            "segment",
            "region",
            "governance_priority_score",
            "risk_tier",
            "main_risk_driver",
            "recommended_action",
        ]
    ].copy()
    risk_export = risk_export.sort_values("governance_priority_score", ascending=False).head(360)
    selected_customers = set(risk_export["customer_id"].astype(str).tolist())

    customer_pricing = _build_customer_pricing_rows(pricing, selected_customers)

    kpi_cube = _round_numeric_columns(
        kpi_cube,
        {
            "net_revenue": 2,
            "weighted_discount_pct": 4,
            "high_discount_revenue_share": 4,
            "margin_at_risk": 2,
            "margin_at_risk_share": 4,
        },
    )
    monthly_agg = _round_numeric_columns(
        monthly_agg,
        {
            "line_revenue": 2,
            "line_list_revenue": 2,
            "discount_weighted_num": 2,
            "high_discount_revenue": 2,
            "margin_risk_revenue": 2,
        },
    )
    customer_pricing = _round_numeric_columns(
        customer_pricing,
        {
            "filtered_revenue": 2,
            "filtered_list_revenue": 2,
            "filtered_discount_num": 2,
        },
    )
    risk_export = _round_numeric_columns(risk_export, {"governance_priority_score": 2})

    filter_options = {
        "segment": [ALL_VALUE] + sorted(pricing["segment"].dropna().unique().tolist()),
        "region": [ALL_VALUE] + sorted(pricing["region"].dropna().unique().tolist()),
        "category": [ALL_VALUE] + sorted(pricing["category"].dropna().unique().tolist()),
        "sales_channel": [ALL_VALUE] + sorted(pricing["sales_channel"].dropna().unique().tolist()),
        "order_month": sorted(pricing["order_month"].dropna().unique().tolist()),
    }

    meta = {
        "coverage_start": pricing["order_date"].min().strftime("%Y-%m-%d"),
        "coverage_end": pricing["order_date"].max().strftime("%Y-%m-%d"),
    }

    payload = {
        "kpiRows": _as_records(kpi_cube),
        "pricingAggRows": _as_records(monthly_agg),
        "customerPricingRows": _as_records(customer_pricing),
        "riskRows": _as_records(risk_export),
        "filterOptions": filter_options,
        "meta": meta,
    }
    data_json = json.dumps(payload, separators=(",", ":"))

    html = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Pricing & Discount Governance Dashboard</title>
  <script src=\"vendor/chart.umd.min.js\"></script>
  <script>
    if (typeof Chart === \"undefined\") {
      document.write('<script src=\"https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js\"><\\/script>');
    }
  </script>
  <style>
    :root {
      color-scheme: light;
      --bg: #edf2fa;
      --bg-radial: #dfeafc;
      --surface: #ffffff;
      --surface-soft: #f5f9ff;
      --ink: #0f172a;
      --muted: #4b5f78;
      --border: #d3deee;
      --hero-start: #10213d;
      --hero-end: #18385f;
      --hero-ink: #eaf2ff;
      --hero-muted: #cfe0ff;
      --hero-chip-bg: rgba(10, 18, 33, 0.35);
      --hero-chip-border: rgba(213, 230, 255, 0.28);
      --input-bg: #ffffff;
      --input-border: #c5d3e8;
      --grid: #e2e8f0;
      --row-hover: #f2f7ff;
      --chart-trend-line: #0f766e;
      --chart-trend-fill: rgba(15, 118, 110, 0.12);
      --chart-segment: #0ea5e9cc;
      --chart-region: #f97316cc;
      --chart-action: #334155cc;
      --shadow: 0 10px 28px rgba(15, 23, 42, 0.08);
      --radius: 14px;
      --focus-ring: 0 0 0 3px rgba(14, 165, 233, 0.28);
    }

    [data-theme="dark"] {
      color-scheme: dark;
      --bg: #0b1322;
      --bg-radial: #13233d;
      --surface: #111a2d;
      --surface-soft: #162238;
      --ink: #e6edf8;
      --muted: #9ab0c9;
      --border: #2b3a54;
      --hero-start: #111b2e;
      --hero-end: #1c3152;
      --hero-ink: #f0f5ff;
      --hero-muted: #b9cbe4;
      --hero-chip-bg: rgba(7, 12, 21, 0.72);
      --hero-chip-border: rgba(154, 176, 201, 0.3);
      --input-bg: #0f1a2d;
      --input-border: #304261;
      --grid: #273750;
      --row-hover: #16253d;
      --chart-trend-line: #34d399;
      --chart-trend-fill: rgba(52, 211, 153, 0.16);
      --chart-segment: #38bdf8cc;
      --chart-region: #fb923ccc;
      --chart-action: #cbd5e1cc;
      --shadow: 0 10px 28px rgba(0, 0, 0, 0.36);
      --focus-ring: 0 0 0 3px rgba(56, 189, 248, 0.26);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      background: radial-gradient(circle at top left, var(--bg-radial) 0, var(--bg) 42%);
      color: var(--ink);
      font-family: \"IBM Plex Sans\", \"Avenir Next\", \"Segoe UI\", sans-serif;
      line-height: 1.45;
      -webkit-font-smoothing: antialiased;
      text-rendering: optimizeLegibility;
      transition: background-color 0.2s ease, color 0.2s ease;
    }

    .page {
      max-width: 1440px;
      margin: 0 auto;
      padding: 20px clamp(12px, 2.2vw, 30px) 28px;
      display: grid;
      gap: 14px;
    }

    .hero {
      background: linear-gradient(138deg, var(--hero-start), var(--hero-end));
      border-radius: var(--radius);
      color: var(--hero-ink);
      box-shadow: var(--shadow);
      padding: 20px clamp(16px, 2.4vw, 30px);
      display: grid;
      gap: 10px;
    }

    .hero-top {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 10px;
      flex-wrap: wrap;
    }

    .hero h1 {
      margin: 0;
      font-size: clamp(1.45rem, 2vw, 1.95rem);
      line-height: 1.2;
      letter-spacing: 0.01em;
    }

    .hero p {
      margin: 0;
      color: var(--hero-muted);
      max-width: 980px;
      font-size: clamp(0.93rem, 1.12vw, 1.02rem);
    }

    .hero-meta {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin: 0;
      padding: 0;
      list-style: none;
      font-size: 0.81rem;
    }

    .hero-meta li {
      background: var(--hero-chip-bg);
      border: 1px solid var(--hero-chip-border);
      border-radius: 999px;
      padding: 4px 9px;
      white-space: nowrap;
    }

    .theme-toggle {
      border: 1px solid var(--hero-chip-border);
      background: var(--hero-chip-bg);
      color: var(--hero-ink);
      min-height: 34px;
      padding: 0 14px;
      border-radius: 999px;
      font-size: 0.82rem;
      font-weight: 700;
      letter-spacing: 0.01em;
      cursor: pointer;
    }

    .theme-toggle:hover { filter: brightness(1.08); }
    .theme-toggle:focus-visible {
      outline: none;
      box-shadow: var(--focus-ring);
    }

    .panel,
    .kpi,
    .chart-card,
    .table-panel {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      box-shadow: var(--shadow);
      min-width: 0;
    }

    .filters {
      padding: 12px;
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 10px;
      align-items: end;
    }

    .field { min-width: 0; }

    .field label {
      display: block;
      margin-bottom: 6px;
      font-size: 0.79rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      color: var(--muted);
    }

    .field select {
      width: 100%;
      min-width: 0;
      height: 40px;
      border-radius: 9px;
      border: 1px solid var(--input-border);
      background: var(--input-bg);
      color: var(--ink);
      font-size: 0.92rem;
      padding: 0 10px;
    }
    .field select:focus-visible {
      outline: none;
      box-shadow: var(--focus-ring);
      border-color: transparent;
    }

    .kpis {
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }

    .kpi {
      padding: 14px;
      display: grid;
      gap: 8px;
      min-height: 112px;
    }

    .kpi-title {
      font-size: 0.79rem;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      color: var(--muted);
      font-weight: 700;
      margin: 0;
    }

    .kpi-value {
      margin: 0;
      font-size: clamp(1.22rem, 1.95vw, 1.82rem);
      font-weight: 700;
      overflow-wrap: anywhere;
      line-height: 1.2;
    }

    .kpi-sub {
      margin: 0;
      font-size: 0.78rem;
      color: var(--muted);
    }

    .charts {
      display: grid;
      gap: 12px;
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .chart-card {
      padding: 12px;
      display: grid;
      gap: 8px;
      min-width: 0;
    }

    .chart-card h3 {
      margin: 0;
      font-size: 0.98rem;
      line-height: 1.25;
      max-width: 92%;
    }

    .chart-card p {
      margin: 0;
      font-size: 0.82rem;
      color: var(--muted);
      max-width: 96%;
    }

    .chart-wrap {
      position: relative;
      width: 100%;
      height: 320px;
      min-height: 280px;
    }
    .chart-wrap canvas {
      width: 100% !important;
      height: 100% !important;
    }

    .table-head {
      padding: 12px 14px;
      border-bottom: 1px solid var(--border);
      background: var(--surface-soft);
    }

    .table-head h3 {
      margin: 0;
      font-size: 1rem;
    }

    .table-head p {
      margin: 5px 0 0 0;
      font-size: 0.82rem;
      color: var(--muted);
    }

    .table-wrap {
      overflow: auto;
      max-height: 560px;
    }

    table {
      width: 100%;
      min-width: 940px;
      border-collapse: collapse;
    }

    th,
    td {
      padding: 9px 10px;
      border-bottom: 1px solid var(--border);
      text-align: left;
      vertical-align: top;
      font-size: 0.85rem;
    }

    th {
      position: sticky;
      top: 0;
      z-index: 1;
      background: var(--surface-soft);
      cursor: pointer;
      user-select: none;
      font-size: 0.78rem;
      text-transform: uppercase;
      letter-spacing: 0.02em;
    }

    .tier-chip {
      display: inline-block;
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 0.73rem;
      font-weight: 700;
      border: 1px solid transparent;
      white-space: nowrap;
    }

    .tier-critical { color: #7f1d1d; background: #fee2e2; border-color: #fecaca; }
    .tier-high { color: #92400e; background: #ffedd5; border-color: #fed7aa; }
    .tier-medium { color: #1d4ed8; background: #dbeafe; border-color: #bfdbfe; }
    .tier-low { color: #14532d; background: #dcfce7; border-color: #bbf7d0; }

    [data-theme="dark"] .tier-critical { color: #fecaca; background: #4a1e24; border-color: #7f1d1d; }
    [data-theme="dark"] .tier-high { color: #fed7aa; background: #4b2b1f; border-color: #92400e; }
    [data-theme="dark"] .tier-medium { color: #bfdbfe; background: #1c335d; border-color: #1d4ed8; }
    [data-theme="dark"] .tier-low { color: #bbf7d0; background: #173928; border-color: #166534; }

    tbody tr:hover td {
      background: var(--row-hover);
    }

    @media (max-width: 1220px) {
      .filters { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .charts { grid-template-columns: 1fr; }
      .chart-wrap { height: 300px; }
    }

    @media (max-width: 720px) {
      .page {
        padding: 14px 10px 20px;
        gap: 10px;
      }

      .filters,
      .kpis {
        grid-template-columns: 1fr;
      }

      .chart-wrap {
        height: 270px;
        min-height: 240px;
      }

      .table-wrap { max-height: 480px; }

      th,
      td {
        font-size: 0.8rem;
        padding: 8px;
      }

      .hero-top { align-items: flex-start; }
    }
  </style>
</head>
<body>
<div class=\"page\">
  <section class=\"hero\">
    <div class=\"hero-top\">
      <h1>Pricing & Discount Governance Executive Dashboard</h1>
      <button id=\"themeToggle\" class=\"theme-toggle\" type=\"button\" aria-label=\"Toggle color mode\">Dark Mode</button>
    </div>
    <p>Executive view of discount intensity, margin exposure, and intervention priorities across commercial segments.</p>
    <ul class=\"hero-meta\">
      <li id=\"coverageMeta\"></li>
    </ul>
  </section>

  <section class=\"panel\">
    <div class=\"filters\">
      <div class=\"field\"><label for=\"segmentFilter\">Segment</label><select id=\"segmentFilter\"></select></div>
      <div class=\"field\"><label for=\"regionFilter\">Region</label><select id=\"regionFilter\"></select></div>
      <div class=\"field\"><label for=\"categoryFilter\">Product Category</label><select id=\"categoryFilter\"></select></div>
      <div class=\"field\"><label for=\"channelFilter\">Sales Channel</label><select id=\"channelFilter\"></select></div>
      <div class=\"field\"><label for=\"periodStartFilter\">Start Month</label><select id=\"periodStartFilter\"></select></div>
      <div class=\"field\"><label for=\"periodEndFilter\">End Month</label><select id=\"periodEndFilter\"></select></div>
    </div>
  </section>

  <section class=\"kpis\">
    <article class=\"kpi\">
      <p class=\"kpi-title\">Net Revenue In Scope</p>
      <p class=\"kpi-value\" id=\"kpiRevenue\">-</p>
      <p class=\"kpi-sub\">Filtered commercial volume</p>
    </article>
    <article class=\"kpi\">
      <p class=\"kpi-title\">Weighted Discount</p>
      <p class=\"kpi-value\" id=\"kpiDiscount\">-</p>
      <p class=\"kpi-sub\">Revenue-weighted realized discount</p>
    </article>
    <article class=\"kpi\">
      <p class=\"kpi-title\">Margin At Risk</p>
      <p class=\"kpi-value\" id=\"kpiMarginRisk\">-</p>
      <p class=\"kpi-sub\">High-discount and low-margin proxy overlap</p>
    </article>
    <article class=\"kpi\">
      <p class=\"kpi-title\">High-Risk Customers</p>
      <p class=\"kpi-value\" id=\"kpiHighRisk\">-</p>
      <p class=\"kpi-sub\">Critical and high tier in current scope</p>
    </article>
  </section>

  <section class=\"charts\">
    <article class=\"chart-card\">
      <h3>Discount Pressure Stayed Elevated Through the Period</h3>
      <p>Monthly weighted discount trend in the selected scope.</p>
      <div class=\"chart-wrap\"><canvas id=\"trendChart\"></canvas></div>
    </article>

    <article class=\"chart-card\">
      <h3>Segment Gap Identifies Where Pricing Discipline Breaks First</h3>
      <p>Weighted discount comparison by segment for the selected non-segment filters.</p>
      <div class=\"chart-wrap\"><canvas id=\"segmentChart\"></canvas></div>
    </article>

    <article class=\"chart-card\">
      <h3>Regional Margin-Risk Concentration Is Uneven</h3>
      <p>Margin-at-risk amount by region under current filters.</p>
      <div class=\"chart-wrap\"><canvas id=\"regionRiskChart\"></canvas></div>
    </article>

    <article class=\"chart-card\">
      <h3>Action Mix Shows Where Governance Capacity Should Go First</h3>
      <p>Revenue in scope grouped by recommended intervention action.</p>
      <div class=\"chart-wrap\"><canvas id=\"actionChart\"></canvas></div>
    </article>
  </section>

  <section class=\"table-panel\">
    <div class=\"table-head\">
      <h3>Highest-Priority Customers (Top 360 Governance Candidates)</h3>
      <p>Use this list to focus reviews on the largest commercial and margin exposures first.</p>
    </div>
    <div class=\"table-wrap\">
      <table id=\"riskTable\">
        <thead>
          <tr>
            <th data-key=\"customer_id\">Customer</th>
            <th data-key=\"segment\">Segment</th>
            <th data-key=\"region\">Region</th>
            <th data-key=\"filtered_revenue\">Revenue</th>
            <th data-key=\"filtered_avg_discount\">Avg Discount</th>
            <th data-key=\"governance_priority_score\">Score</th>
            <th data-key=\"risk_tier\">Risk Tier</th>
            <th data-key=\"recommended_action\">Recommended Action</th>
          </tr>
        </thead>
        <tbody></tbody>
      </table>
    </div>
  </section>

</div>

<script>
const DATA = __DATA_JSON__;
const ALL = "__ALL_VALUE__";
const THEME_STORAGE_KEY = 'pricing_dashboard_theme';

Chart.defaults.font.family = 'IBM Plex Sans, Avenir Next, Segoe UI, sans-serif';
Chart.defaults.color = '#475569';
Chart.defaults.borderColor = '#e2e8f0';
Chart.defaults.plugins.legend.labels.usePointStyle = true;
Chart.defaults.plugins.legend.labels.boxWidth = 10;

const filterEls = {
  segment: document.getElementById('segmentFilter'),
  region: document.getElementById('regionFilter'),
  category: document.getElementById('categoryFilter'),
  sales_channel: document.getElementById('channelFilter'),
  period_start: document.getElementById('periodStartFilter'),
  period_end: document.getElementById('periodEndFilter')
};
const themeToggleEl = document.getElementById('themeToggle');

const charts = {};
const tableState = { key: 'governance_priority_score', dir: 'desc' };

const fmtCurrency = (n) => n.toLocaleString('en-US', {
  style: 'currency',
  currency: 'USD',
  maximumFractionDigits: 0
});

const fmtPct = (n, digits = 1) => `${(n * 100).toFixed(digits)}%`;

const fmtAxisUsd = (value) => {
  const v = Number(value) || 0;
  if (Math.abs(v) >= 1_000_000_000) return `$${(v / 1_000_000_000).toFixed(1)}B`;
  if (Math.abs(v) >= 1_000_000) return `$${(v / 1_000_000).toFixed(1)}M`;
  if (Math.abs(v) >= 1_000) return `$${(v / 1_000).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
};

const dims = ['segment', 'region', 'category', 'sales_channel'];

function getCssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function getThemePalette() {
  return {
    axisText: getCssVar('--muted'),
    grid: getCssVar('--grid'),
    trendLine: getCssVar('--chart-trend-line'),
    trendFill: getCssVar('--chart-trend-fill'),
    segment: getCssVar('--chart-segment'),
    region: getCssVar('--chart-region'),
    action: getCssVar('--chart-action')
  };
}

function updateThemeToggleLabel(theme) {
  if (!themeToggleEl) return;
  themeToggleEl.textContent = theme === 'dark' ? 'Switch to Light Mode' : 'Switch to Dark Mode';
}

function applyTheme(theme, persist = false) {
  const resolved = theme === 'dark' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', resolved);
  Chart.defaults.color = getCssVar('--muted');
  Chart.defaults.borderColor = getCssVar('--grid');
  updateThemeToggleLabel(resolved);

  if (persist) {
    try { localStorage.setItem(THEME_STORAGE_KEY, resolved); } catch (_) {}
  }
}

function initialTheme() {
  let stored = null;
  try { stored = localStorage.getItem(THEME_STORAGE_KEY); } catch (_) {}
  if (stored === 'light' || stored === 'dark') return stored;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function fmtMonth(yyyymm) {
  if (!yyyymm || !/^\\d{4}-\\d{2}$/.test(yyyymm)) return yyyymm || '';
  const [year, month] = yyyymm.split('-');
  const dt = new Date(Number(year), Number(month) - 1, 1);
  return dt.toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
}

function compactLabel(label, maxLen = 26) {
  const value = String(label || '');
  if (value.length <= maxLen) return value;
  return `${value.slice(0, maxLen - 3)}...`;
}

function populateSelect(el, values) {
  el.innerHTML = values.map((v) => `<option value=\"${v}\">${v}</option>`).join('');
}

function getFilters() {
  const periodStart = filterEls.period_start.value;
  const periodEnd = filterEls.period_end.value;
  const normalizedStart = periodStart <= periodEnd ? periodStart : periodEnd;
  const normalizedEnd = periodStart <= periodEnd ? periodEnd : periodStart;
  return {
    segment: filterEls.segment.value,
    region: filterEls.region.value,
    category: filterEls.category.value,
    sales_channel: filterEls.sales_channel.value,
    period_start: normalizedStart,
    period_end: normalizedEnd
  };
}

function matchesBaseRow(row, filters) {
  return dims.every((dim) => filters[dim] === ALL || row[dim] === filters[dim]);
}

function matchesPeriod(row, filters) {
  if (!row.order_month) return true;
  return row.order_month >= filters.period_start && row.order_month <= filters.period_end;
}

function makeOrUpdateChart(id, config) {
  if (charts[id]) {
    charts[id].data = config.data;
    charts[id].options = config.options;
    charts[id].update();
    return;
  }
  charts[id] = new Chart(document.getElementById(id), config);
}

function aggregateScopedPricing(filters) {
  const agg = {
    line_revenue: 0,
    line_list_revenue: 0,
    discount_weighted_num: 0,
    margin_risk_revenue: 0
  };

  DATA.pricingAggRows.forEach((row) => {
    if (!matchesBaseRow(row, filters) || !matchesPeriod(row, filters)) return;
    agg.line_revenue += Number(row.line_revenue) || 0;
    agg.line_list_revenue += Number(row.line_list_revenue) || 0;
    agg.discount_weighted_num += Number(row.discount_weighted_num) || 0;
    agg.margin_risk_revenue += Number(row.margin_risk_revenue) || 0;
  });

  return {
    net_revenue: agg.line_revenue,
    weighted_discount_pct: agg.line_list_revenue > 0 ? agg.discount_weighted_num / agg.line_list_revenue : 0,
    margin_at_risk: agg.margin_risk_revenue
  };
}

function buildCustomerPricingMap(filters) {
  const map = new Map();
  DATA.customerPricingRows.forEach((row) => {
    if (!matchesBaseRow(row, filters) || !matchesPeriod(row, filters)) return;

    const id = row.customer_id;
    if (!map.has(id)) {
      map.set(id, {
        filtered_revenue: 0,
        filtered_list_revenue: 0,
        filtered_discount_num: 0
      });
    }

    const acc = map.get(id);
    acc.filtered_revenue += Number(row.filtered_revenue) || 0;
    acc.filtered_list_revenue += Number(row.filtered_list_revenue) || 0;
    acc.filtered_discount_num += Number(row.filtered_discount_num) || 0;
  });
  return map;
}

function scopedRiskRows(filters) {
  const customerPricingMap = buildCustomerPricingMap(filters);
  const rows = [];

  DATA.riskRows.forEach((row) => {
    if ((filters.segment !== ALL && row.segment !== filters.segment) ||
        (filters.region !== ALL && row.region !== filters.region)) {
      return;
    }

    const scope = customerPricingMap.get(row.customer_id);
    if (!scope || scope.filtered_revenue <= 0) return;

    rows.push({
      ...row,
      filtered_revenue: scope.filtered_revenue,
      filtered_avg_discount:
        scope.filtered_list_revenue > 0 ? scope.filtered_discount_num / scope.filtered_list_revenue : 0
    });
  });

  return rows;
}

function updateKpis(filters, riskRows) {
  const kpi = aggregateScopedPricing(filters);
  document.getElementById('kpiRevenue').textContent = fmtCurrency(Number(kpi.net_revenue) || 0);
  document.getElementById('kpiDiscount').textContent = fmtPct(Number(kpi.weighted_discount_pct) || 0);
  document.getElementById('kpiMarginRisk').textContent = fmtCurrency(Number(kpi.margin_at_risk) || 0);

  const highRiskCount = riskRows.filter((r) => r.risk_tier === 'High' || r.risk_tier === 'Critical').length;
  document.getElementById('kpiHighRisk').textContent = highRiskCount.toLocaleString('en-US');
}

function updateTrendChart(filters) {
  const palette = getThemePalette();
  const buckets = new Map();

  DATA.pricingAggRows.forEach((row) => {
    if (!matchesBaseRow(row, filters) || !matchesPeriod(row, filters)) return;

    const month = row.order_month;
    if (!buckets.has(month)) {
      buckets.set(month, {
        list_revenue: 0,
        discount_weighted_num: 0
      });
    }

    const acc = buckets.get(month);
    acc.list_revenue += Number(row.line_list_revenue) || 0;
    acc.discount_weighted_num += Number(row.discount_weighted_num) || 0;
  });

  const monthly = [...buckets.entries()]
    .sort((a, b) => String(a[0]).localeCompare(String(b[0])))
    .map(([month, val]) => ({
      month,
      weighted_discount_pct: val.list_revenue > 0 ? val.discount_weighted_num / val.list_revenue : 0
    }));

  makeOrUpdateChart('trendChart', {
    type: 'line',
    data: {
      labels: monthly.map((r) => fmtMonth(r.month)),
      datasets: [{
        label: 'Weighted discount (%)',
        data: monthly.map((r) => r.weighted_discount_pct * 100),
        borderColor: palette.trendLine,
        backgroundColor: palette.trendFill,
        pointRadius: 0,
        pointHitRadius: 8,
        borderWidth: 2,
        tension: 0.28,
        fill: true
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: { legend: { display: false } },
      scales: {
        x: {
          ticks: {
            autoSkip: true,
            maxTicksLimit: 8,
            color: palette.axisText
          },
          grid: { display: false }
        },
        y: {
          beginAtZero: true,
          ticks: {
            maxTicksLimit: 6,
            color: palette.axisText,
            callback: (v) => `${Number(v).toFixed(0)}%`
          },
          grid: { color: palette.grid }
        }
      }
    }
  });
}

function updateSegmentChart(filters) {
  const palette = getThemePalette();
  const grouped = new Map();
  DATA.pricingAggRows.forEach((row) => {
    if (!matchesPeriod(row, filters)) return;
    if (filters.region !== ALL && row.region !== filters.region) return;
    if (filters.category !== ALL && row.category !== filters.category) return;
    if (filters.sales_channel !== ALL && row.sales_channel !== filters.sales_channel) return;
    if (filters.segment !== ALL && row.segment !== filters.segment) return;

    const key = row.segment;
    if (!grouped.has(key)) {
      grouped.set(key, { discount_weighted_num: 0, line_list_revenue: 0 });
    }
    const acc = grouped.get(key);
    acc.discount_weighted_num += Number(row.discount_weighted_num) || 0;
    acc.line_list_revenue += Number(row.line_list_revenue) || 0;
  });

  const rows = [...grouped.entries()]
    .map(([segment, v]) => ({
      segment,
      weighted_discount_pct: v.line_list_revenue > 0 ? v.discount_weighted_num / v.line_list_revenue : 0
    }))
    .sort((a, b) => Number(b.weighted_discount_pct) - Number(a.weighted_discount_pct));

  makeOrUpdateChart('segmentChart', {
    type: 'bar',
    data: {
      labels: rows.map((r) => r.segment),
      datasets: [{
        label: 'Weighted discount (%)',
        data: rows.map((r) => (Number(r.weighted_discount_pct) || 0) * 100),
        backgroundColor: palette.segment,
        borderRadius: 6,
        maxBarThickness: 54
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: {
          ticks: {
            color: palette.axisText,
            callback: (_, i) => compactLabel(rows[i]?.segment || '', 16)
          },
          grid: { display: false }
        },
        y: {
          beginAtZero: true,
          ticks: {
            maxTicksLimit: 6,
            color: palette.axisText,
            callback: (v) => `${Number(v).toFixed(0)}%`
          },
          grid: { color: palette.grid }
        }
      }
    }
  });
}

function updateRegionRiskChart(filters) {
  const palette = getThemePalette();
  const grouped = new Map();
  DATA.pricingAggRows.forEach((row) => {
    if (!matchesPeriod(row, filters)) return;
    if (filters.segment !== ALL && row.segment !== filters.segment) return;
    if (filters.category !== ALL && row.category !== filters.category) return;
    if (filters.sales_channel !== ALL && row.sales_channel !== filters.sales_channel) return;
    if (filters.region !== ALL && row.region !== filters.region) return;

    const key = row.region;
    if (!grouped.has(key)) grouped.set(key, 0);
    grouped.set(key, grouped.get(key) + (Number(row.margin_risk_revenue) || 0));
  });

  const rows = [...grouped.entries()]
    .map(([region, margin_at_risk]) => ({ region, margin_at_risk }))
    .sort((a, b) => Number(b.margin_at_risk) - Number(a.margin_at_risk));

  makeOrUpdateChart('regionRiskChart', {
    type: 'bar',
    data: {
      labels: rows.map((r) => r.region),
      datasets: [{
        label: 'Margin at risk',
        data: rows.map((r) => Number(r.margin_at_risk) || 0),
        backgroundColor: palette.region,
        borderRadius: 6,
        maxBarThickness: 54
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { display: false } },
      scales: {
        x: {
          ticks: {
            color: palette.axisText,
            callback: (_, i) => compactLabel(rows[i]?.region || '', 16)
          },
          grid: { display: false }
        },
        y: {
          beginAtZero: true,
          ticks: {
            maxTicksLimit: 6,
            color: palette.axisText,
            callback: (v) => fmtAxisUsd(v)
          },
          grid: { color: palette.grid }
        }
      }
    }
  });
}

function updateActionChart(riskRows) {
  const palette = getThemePalette();
  const grouped = new Map();
  riskRows.forEach((row) => {
    const key = row.recommended_action;
    const current = grouped.get(key) || 0;
    grouped.set(key, current + (Number(row.filtered_revenue) || 0));
  });

  const rows = [...grouped.entries()]
    .map(([label, value]) => ({ label, value }))
    .sort((a, b) => b.value - a.value);

  makeOrUpdateChart('actionChart', {
    type: 'bar',
    data: {
      labels: rows.map((r) => compactLabel(r.label, 28)),
      datasets: [{
        label: 'Revenue in scope',
        data: rows.map((r) => r.value),
        backgroundColor: palette.action,
        borderRadius: 6,
        maxBarThickness: 52
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: 'y',
      plugins: { legend: { display: false } },
      scales: {
        y: {
          ticks: { autoSkip: false, color: palette.axisText, font: { size: 11 } },
          grid: { display: false }
        },
        x: {
          beginAtZero: true,
          ticks: {
            maxTicksLimit: 6,
            color: palette.axisText,
            callback: (v) => fmtAxisUsd(v)
          },
          grid: { color: palette.grid }
        }
      }
    }
  });
}

function tierChip(tier) {
  const cls = {
    Critical: 'tier-chip tier-critical',
    High: 'tier-chip tier-high',
    Medium: 'tier-chip tier-medium',
    Low: 'tier-chip tier-low'
  }[tier] || 'tier-chip';

  return `<span class=\"${cls}\">${tier}</span>`;
}

function sortRows(rows) {
  const key = tableState.key;
  const dir = tableState.dir === 'asc' ? 1 : -1;

  return [...rows].sort((a, b) => {
    const av = a[key];
    const bv = b[key];

    if (typeof av === 'number' && typeof bv === 'number') {
      return (av - bv) * dir;
    }
    return String(av).localeCompare(String(bv)) * dir;
  });
}

function renderTable(riskRows) {
  const sorted = sortRows(riskRows).slice(0, 160);
  const tbody = document.querySelector('#riskTable tbody');

  tbody.innerHTML = sorted.map((r) => `
    <tr>
      <td>${r.customer_id}</td>
      <td>${r.segment}</td>
      <td>${r.region}</td>
      <td>${fmtCurrency(Number(r.filtered_revenue) || 0)}</td>
      <td>${fmtPct(Number(r.filtered_avg_discount) || 0)}</td>
      <td>${(Number(r.governance_priority_score) || 0).toFixed(1)}</td>
      <td>${tierChip(r.risk_tier)}</td>
      <td>${r.recommended_action}</td>
    </tr>
  `).join('');
}

function initMeta() {
  document.getElementById('coverageMeta').textContent =
    `Commercial window: ${DATA.meta.coverage_start} to ${DATA.meta.coverage_end}`;
}

function setPeriodOptions() {
  const months = DATA.filterOptions.order_month || [];
  const options = months.map((m) => `<option value="${m}">${m}</option>`).join('');
  filterEls.period_start.innerHTML = options;
  filterEls.period_end.innerHTML = options;

  if (months.length > 0) {
    filterEls.period_start.value = months[0];
    filterEls.period_end.value = months[months.length - 1];
  }
}

function updateSelectedPeriodMeta(filters) {
  document.getElementById('coverageMeta').textContent =
    `Commercial window: ${DATA.meta.coverage_start} to ${DATA.meta.coverage_end} | Current view: ${fmtMonth(filters.period_start)} to ${fmtMonth(filters.period_end)}`;
}

function updateAll() {
  const filters = getFilters();
  const riskRows = scopedRiskRows(filters);

  updateSelectedPeriodMeta(filters);
  updateKpis(filters, riskRows);
  updateTrendChart(filters);
  updateSegmentChart(filters);
  updateRegionRiskChart(filters);
  updateActionChart(riskRows);
  renderTable(riskRows);
}

function init() {
  populateSelect(filterEls.segment, DATA.filterOptions.segment);
  populateSelect(filterEls.region, DATA.filterOptions.region);
  populateSelect(filterEls.category, DATA.filterOptions.category);
  populateSelect(filterEls.sales_channel, DATA.filterOptions.sales_channel);
  setPeriodOptions();

  Object.values(filterEls).forEach((el) => el.addEventListener('change', updateAll));

  document.querySelectorAll('#riskTable thead th').forEach((th) => {
    th.addEventListener('click', () => {
      const key = th.getAttribute('data-key');
      if (tableState.key === key) {
        tableState.dir = tableState.dir === 'asc' ? 'desc' : 'asc';
      } else {
        tableState.key = key;
        tableState.dir = 'desc';
      }
      updateAll();
    });
  });

  applyTheme(initialTheme(), false);
  if (themeToggleEl) {
    themeToggleEl.addEventListener('click', () => {
      const current = document.documentElement.getAttribute('data-theme') === 'dark' ? 'dark' : 'light';
      const next = current === 'dark' ? 'light' : 'dark';
      applyTheme(next, true);
      updateAll();
    });
  }

  initMeta();
  updateAll();
}

init();
</script>
</body>
</html>
"""

    html = html.replace("__DATA_JSON__", data_json).replace("__ALL_VALUE__", ALL_VALUE)

    dashboard_path = dashboard_dir / "pricing_discount_governance_dashboard.html"
    dashboard_path.write_text(html, encoding="utf-8")
    return dashboard_path
