"""Self-contained executive dashboard builder.

The module is intentionally large because the dashboard is a single
versioned artifact (~3.5 MB self-contained HTML with embedded JSON
payload, CSS, and Chart.js bindings). Splitting the template across
files would multiply the contracts that have to stay in lockstep with
the pre-aggregated `kpi_cube` / `monthly_agg` / `risk_export` payloads
without reducing the actual surface area you need to read together.

The structure is:
- Helpers (rows ~30-150): data shaping, KPI cube, monthly agg, customer slice
- `build_executive_dashboard` (rows ~158-end): payload assembly +
  HTML/CSS/JS template that renders the dashboard for GitHub Pages.

Output: writes the dashboard HTML and copies the local Chart.js vendor
asset under `dashboard_dir/`. Returns the path to the HTML file.
"""

from __future__ import annotations

import json
import shutil
from itertools import combinations
from pathlib import Path

import numpy as np
import pandas as pd

ALL_VALUE = "All"

DEFAULT_DASHBOARD_POLICY = {
    "posture_thresholds": {
        "weighted_discount_warn": 0.14,
        "weighted_discount_critical": 0.20,
        "margin_risk_share_warn": 0.12,
        "margin_risk_share_critical": 0.20,
        "high_risk_count_warn": 35,
        "high_risk_count_critical": 80,
    },
    "kpi_card_thresholds": {
        "weighted_discount_warn": 0.14,
        "weighted_discount_critical": 0.20,
        "margin_risk_share_warn": 0.12,
        "margin_risk_share_critical": 0.20,
        "high_risk_count_warn": 35,
        "high_risk_count_critical": 80,
    },
}


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


def _load_dashboard_policy() -> dict:
    policy_path = Path(__file__).resolve().parents[2] / "config" / "dashboard_policy.json"
    if not policy_path.exists():
        return DEFAULT_DASHBOARD_POLICY
    try:
        payload = json.loads(policy_path.read_text(encoding="utf-8"))
        if isinstance(payload, dict):
            return payload
    except (OSError, json.JSONDecodeError):
        pass
    return DEFAULT_DASHBOARD_POLICY


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
    processed_tables: dict[str, pd.DataFrame],
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
            "total_orders",
            "avg_discount_pct",
            "share_orders_high_discount",
            "revenue_high_discount_share",
            "avg_margin_proxy_pct",
            "pricing_risk_score",
            "discount_dependency_score",
            "margin_erosion_score",
            "governance_priority_score",
            "risk_tier",
            "main_risk_driver",
            "recommended_action",
        ]
    ].copy()
    risk_export = risk_export.sort_values("governance_priority_score", ascending=False).head(140)
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
        "pricing_rows": int(len(pricing)),
        "customers": int(pricing["customer_id"].nunique()),
        "risk_customers_exported": int(len(risk_export)),
    }

    payload = {
        "kpiRows": _as_records(kpi_cube),
        "pricingAggRows": _as_records(monthly_agg),
        "customerPricingRows": _as_records(customer_pricing),
        "riskRows": _as_records(risk_export),
        "filterOptions": filter_options,
        "meta": meta,
        "policy": _load_dashboard_policy(),
    }
    data_json = json.dumps(payload, separators=(",", ":"))

    html = """<!doctype html>
<html lang=\"en\">
<head>
  <meta charset=\"utf-8\" />
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\" />
  <title>Pricing &amp; Discount Governance Dashboard</title>
  <meta name=\"description\" content=\"Synthetic pricing governance analytics dashboard for detecting discount leakage, margin exposure, and commercial risk.\" />
  <meta name=\"theme-color\" content=\"#102033\" />
  <link rel=\"canonical\" href=\"https://mfidalgomartins.github.io/pricing-discount-governance-system/pricing-discipline-command-center.html\" />
  <meta property=\"og:title\" content=\"Pricing &amp; Discount Governance Dashboard\" />
  <meta property=\"og:description\" content=\"Synthetic pricing governance analytics dashboard for discount leakage, margin exposure, and customer-level intervention planning.\" />
  <meta property=\"og:type\" content=\"website\" />
  <meta property=\"og:url\" content=\"https://mfidalgomartins.github.io/pricing-discount-governance-system/pricing-discipline-command-center.html\" />
  <meta name=\"twitter:card\" content=\"summary_large_image\" />
  <script src=\"vendor/chart.umd.min.js\"></script>
  <link rel=\"preconnect\" href=\"https://fonts.googleapis.com\" />
  <link rel=\"preconnect\" href=\"https://fonts.gstatic.com\" crossorigin />
  <link href=\"https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,400;9..144,500;9..144,600&family=IBM+Plex+Sans:wght@400;500;600&family=IBM+Plex+Mono:wght@400;500&display=swap\" rel=\"stylesheet\" />
  <style>
    :root {
      color-scheme: light;
      --font-display: \"Fraunces\", Georgia, \"Times New Roman\", serif;
      --font-sans: \"IBM Plex Sans\", -apple-system, BlinkMacSystemFont, \"Helvetica Neue\", Arial, sans-serif;
      --font-mono: \"IBM Plex Mono\", ui-monospace, Menlo, Consolas, monospace;

      --paper:     #f4f1ea;
      --surface:   #fbfaf6;
      --surface-2: #ffffff;
      --ink:       #1a1a1a;
      --ink-2:     #2a2a2a;
      --muted:     #6c655e;
      --muted-2:   #8a8278;
      --rule:      rgba(26, 26, 26, 0.10);
      --rule-2:    rgba(26, 26, 26, 0.18);
      --rule-3:    rgba(26, 26, 26, 0.32);

      --accent-risk: #8c2920;
      --accent-warn: #936323;
      --accent-ok:   #3c5d2e;
      --accent-info: #1a1a1a;

      --accent-risk-soft: rgba(140, 41, 32, 0.08);
      --accent-warn-soft: rgba(147, 99, 35, 0.10);
      --accent-ok-soft:   rgba(60, 93, 46, 0.10);

      /* Chart palette (read by JS via getCssVar) */
      --muted-chart:        #6c655e;
      --grid:               rgba(26, 26, 26, 0.08);
      --chart-trend-line:   #1a1a1a;
      --chart-trend-fill:   rgba(26, 26, 26, 0.06);
      --chart-segment:      #8c2920;
      --chart-region:       #936323;
      --chart-region-text:  #6c4a18;
      --chart-action:       #3c5d2e;

      --shadow:      0 1px 0 var(--rule);
      --shadow-soft: 0 1px 0 var(--rule);

      --radius:    0px;
      --radius-sm: 2px;
      --focus-ring: 0 0 0 2px var(--paper), 0 0 0 4px var(--ink);

      --page-max: 1280px;

      --tone-ok-bg:        var(--accent-ok-soft);
      --tone-warn-bg:      var(--accent-warn-soft);
      --tone-critical-bg:  var(--accent-risk-soft);
      --tone-neutral-bg:   rgba(26, 26, 26, 0.05);

      --ok:        var(--accent-ok);
      --warn:      var(--accent-warn);
      --critical:  var(--accent-risk);
      --neutral:   var(--ink);

      /* Legacy aliases kept so dark-mode overrides still work */
      --bg: var(--paper);
      --bg-radial: var(--paper);
      --border: var(--rule-2);
      --row-hover: rgba(26, 26, 26, 0.03);
      --row-alt: rgba(26, 26, 26, 0.015);
    }

    [data-theme=\"dark\"] {
      color-scheme: dark;
      --paper:     #161510;
      --surface:   #1c1b16;
      --surface-2: #25241e;
      --ink:       #f0ebde;
      --ink-2:     #d8d3c5;
      --muted:     #968f80;
      --muted-2:   #756f63;
      --rule:      rgba(240, 235, 222, 0.12);
      --rule-2:    rgba(240, 235, 222, 0.22);
      --rule-3:    rgba(240, 235, 222, 0.36);

      --accent-risk: #d57460;
      --accent-warn: #c79352;
      --accent-ok:   #8eaf72;
      --accent-info: var(--ink);

      --accent-risk-soft: rgba(213, 116, 96, 0.16);
      --accent-warn-soft: rgba(199, 147, 82, 0.16);
      --accent-ok-soft:   rgba(142, 175, 114, 0.16);

      --muted-chart:        #b3a994;
      --grid:               rgba(240, 235, 222, 0.10);
      --chart-trend-line:   #f0ebde;
      --chart-trend-fill:   rgba(240, 235, 222, 0.10);
      --chart-segment:      #d57460;
      --chart-region:       #c79352;
      --chart-region-text:  #c79352;
      --chart-action:       #8eaf72;

      --bg: var(--paper);
      --row-hover: rgba(240, 235, 222, 0.05);
      --row-alt: rgba(240, 235, 222, 0.02);
    }

    *, *::before, *::after { box-sizing: border-box; }

    html { -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }

    body {
      margin: 0;
      font-family: var(--font-sans);
      background: var(--paper);
      color: var(--ink);
      font-size: 15px;
      line-height: 1.55;
      font-feature-settings: \"ss01\", \"cv11\";
      letter-spacing: -0.005em;
    }

    .skip-link {
      position: absolute; left: -9999px; top: -9999px;
      background: var(--ink); color: var(--paper);
      padding: 8px 14px; font-size: 12px;
      letter-spacing: 0.08em; text-transform: uppercase;
      z-index: 99;
    }
    .skip-link:focus { left: 16px; top: 16px; }

    .page {
      max-width: var(--page-max);
      margin: 0 auto;
      padding: 56px 40px 80px;
      display: flex; flex-direction: column;
      gap: 56px;
    }

    /* ---------------- HERO ---------------- */

    .hero { padding: 0; }

    .hero-grid {
      display: grid;
      grid-template-columns: 1fr;
      gap: 32px;
    }

    .hero-top {
      display: flex; align-items: flex-start; justify-content: space-between;
      gap: 24px; flex-wrap: wrap;
    }

    .hero h1 {
      font-family: var(--font-display);
      font-weight: 500;
      font-size: clamp(40px, 6.4vw, 72px);
      line-height: 1.02;
      letter-spacing: -0.025em;
      margin: 0;
      color: var(--ink);
      font-variation-settings: \"opsz\" 120, \"SOFT\" 30;
      max-width: 18ch;
    }

    .hero-actions { display: inline-flex; gap: 8px; }

    .theme-toggle, .print-btn, .reset-btn {
      font-family: var(--font-sans);
      font-size: 11px;
      letter-spacing: 0.10em;
      text-transform: uppercase;
      font-weight: 500;
      background: transparent;
      border: 1px solid var(--rule-2);
      color: var(--ink-2);
      padding: 8px 14px;
      border-radius: var(--radius-sm);
      cursor: pointer;
      transition: border-color 0.15s, color 0.15s, background 0.15s;
    }
    .theme-toggle:hover, .print-btn:hover, .reset-btn:hover {
      border-color: var(--ink); color: var(--ink);
    }
    .theme-toggle:focus-visible, .print-btn:focus-visible, .reset-btn:focus-visible {
      outline: none; box-shadow: var(--focus-ring);
    }

    .hero-subtitle {
      font-family: var(--font-display);
      font-weight: 400;
      font-size: clamp(18px, 2.0vw, 22px);
      line-height: 1.45;
      color: var(--ink-2);
      letter-spacing: -0.01em;
      margin: 0;
      max-width: 68ch;
      font-style: italic;
    }

    .hero-callout {
      font-family: var(--font-sans);
      font-size: 15px;
      line-height: 1.65;
      color: var(--muted);
      margin: 0;
      max-width: 72ch;
    }

    /* Decision grid: rule-separated columns, not stacked cards */
    .decision-grid {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: 0;
      margin-top: 8px;
      border-top: 1px solid var(--rule-2);
    }

    .decision-card {
      display: flex; flex-direction: column;
      gap: 6px;
      padding: 20px 24px 20px 0;
      border-right: 1px solid var(--rule);
    }
    .decision-card:last-child { border-right: none; padding-right: 0; }
    .decision-card:not(:first-child) { padding-left: 24px; }

    .decision-label {
      font-family: var(--font-sans);
      font-size: 10px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--muted-2);
      font-weight: 500;
    }
    .decision-value {
      font-family: var(--font-display);
      font-weight: 500;
      font-size: 24px;
      line-height: 1.15;
      color: var(--ink);
      letter-spacing: -0.015em;
    }
    .decision-note {
      font-size: 13px; line-height: 1.5; color: var(--muted);
    }

    .hero-meta {
      list-style: none; margin: 0; padding: 0;
      display: flex; flex-wrap: wrap; gap: 0;
      font-size: 12px; color: var(--muted-2);
      letter-spacing: 0.02em;
    }
    .hero-meta li {
      padding: 0 14px;
      border-right: 1px solid var(--rule);
    }
    .hero-meta li:first-child { padding-left: 0; }
    .hero-meta li:last-child { border-right: none; padding-right: 0; }

    /* Hide overdesigned hero rail — keep DOM for JS, but visually quiet it */
    .hero-rail { display: none; }

    /* ---------------- SECTION HEADERS ---------------- */

    .section-head {
      display: flex; align-items: end; justify-content: space-between;
      gap: 32px; flex-wrap: wrap;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--rule-2);
    }
    .section-head-copy { display: flex; flex-direction: column; gap: 6px; }

    .section-kicker {
      font-family: var(--font-sans);
      font-size: 10px;
      letter-spacing: 0.16em;
      text-transform: uppercase;
      color: var(--muted-2);
      font-weight: 500;
    }
    .section-head h2 {
      font-family: var(--font-display);
      font-weight: 500;
      font-size: clamp(28px, 3.2vw, 38px);
      line-height: 1.1;
      letter-spacing: -0.02em;
      margin: 0;
      color: var(--ink);
    }
    .section-head p {
      font-size: 14px; color: var(--muted);
      max-width: 56ch; margin: 0;
    }

    /* ---------------- PANELS ---------------- */

    .panel {
      background: transparent;
      padding: 0;
      border: none;
    }

    /* ---------------- FILTERS ---------------- */

    .filters-panel { display: flex; flex-direction: column; gap: 20px; }

    .filters-head {
      display: flex; align-items: end; justify-content: space-between;
      gap: 24px; flex-wrap: wrap;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--rule-2);
    }
    .filters-head-copy { display: flex; flex-direction: column; gap: 6px; }
    .filters-head h2 {
      font-family: var(--font-display);
      font-weight: 500;
      font-size: 24px;
      line-height: 1.15;
      letter-spacing: -0.015em;
      margin: 0; color: var(--ink);
    }
    .filters-head p { font-size: 13px; color: var(--muted); margin: 0; }

    .controls-row { display: flex; align-items: center; }
    .controls-meta {
      font-family: var(--font-mono);
      font-size: 11.5px;
      color: var(--muted);
      margin: 0;
      letter-spacing: 0;
    }

    .filters {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 16px 20px;
    }
    .field { display: flex; flex-direction: column; gap: 6px; }
    .field label {
      font-family: var(--font-sans);
      font-size: 10px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--muted-2);
      font-weight: 500;
    }
    .field select {
      font-family: var(--font-sans);
      font-size: 14px;
      color: var(--ink);
      background: transparent;
      border: none;
      border-bottom: 1px solid var(--rule-2);
      padding: 6px 24px 6px 0;
      appearance: none;
      -webkit-appearance: none;
      background-image: linear-gradient(45deg, transparent 50%, var(--muted) 50%), linear-gradient(135deg, var(--muted) 50%, transparent 50%);
      background-position: right 6px center, right 1px center;
      background-size: 5px 5px, 5px 5px;
      background-repeat: no-repeat;
      cursor: pointer;
      border-radius: 0;
      transition: border-color 0.15s;
    }
    .field select:hover { border-bottom-color: var(--ink); }
    .field select:focus-visible {
      outline: none;
      border-bottom-color: var(--ink);
      box-shadow: 0 1px 0 var(--ink);
    }

    /* ---------------- KPIs ---------------- */

    .kpis {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 0;
      border-top: 1px solid var(--rule-3);
      border-bottom: 1px solid var(--rule-2);
    }
    .kpi {
      display: flex; flex-direction: column;
      gap: 14px;
      padding: 28px 28px 28px 0;
      border-right: 1px solid var(--rule);
      background: transparent;
      position: relative;
    }
    .kpi:last-child { border-right: none; padding-right: 0; }
    .kpi:not(:first-child) { padding-left: 28px; }

    .kpi-head {
      display: flex; align-items: center; justify-content: space-between;
      gap: 12px;
    }
    .kpi-title {
      font-family: var(--font-sans);
      font-size: 11px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--muted);
      font-weight: 500;
      margin: 0;
    }

    .kpi-state {
      font-family: var(--font-sans);
      font-size: 10px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      font-weight: 500;
      padding: 2px 8px;
      border: 1px solid currentColor;
      border-radius: var(--radius-sm);
      color: var(--muted);
      background: transparent;
    }
    .kpi-state-ok       { color: var(--accent-ok); }
    .kpi-state-warn     { color: var(--accent-warn); }
    .kpi-state-critical { color: var(--accent-risk); }
    .kpi-state-neutral  { color: var(--muted); }

    .kpi-value {
      font-family: var(--font-display);
      font-weight: 500;
      font-size: clamp(36px, 4.2vw, 52px);
      line-height: 1.0;
      letter-spacing: -0.025em;
      color: var(--ink);
      margin: 0;
      font-variation-settings: \"opsz\" 96;
      font-variant-numeric: tabular-nums;
    }
    .kpi-sub {
      font-size: 13px;
      color: var(--muted);
      line-height: 1.5;
      margin: 0;
    }
    .kpi-detail {
      font-family: var(--font-mono);
      font-size: 11.5px;
      line-height: 1.5;
      color: var(--muted-2);
      margin: 0;
      letter-spacing: 0;
    }

    /* Color the kpi-value subtly in warning/critical states via class on the article */
    .kpi-critical .kpi-value { color: var(--accent-risk); }
    .kpi-warn .kpi-value     { color: var(--ink); }
    .kpi-ok .kpi-value       { color: var(--ink); }

    /* ---------------- INSIGHT STRIP ---------------- */

    .insight-strip {
      padding: 0;
      border-top: 1px solid var(--rule);
      padding-top: 28px;
    }
    .insight-layout {
      display: grid;
      grid-template-columns: 1.5fr 1fr;
      gap: 48px;
    }
    .insight-summary, .insight-action {
      display: flex; flex-direction: column; gap: 12px;
    }
    .insight-label {
      font-family: var(--font-sans);
      font-size: 10px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--muted-2);
      font-weight: 500;
    }
    .insight-main {
      font-family: var(--font-display);
      font-weight: 400;
      font-size: clamp(18px, 1.8vw, 22px);
      line-height: 1.45;
      letter-spacing: -0.01em;
      color: var(--ink);
      margin: 0;
      max-width: 56ch;
    }
    .insight-chips {
      display: flex; flex-wrap: wrap; gap: 6px;
      margin-top: 4px;
    }
    .chip, .insight-chips > * {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--muted);
      border: 1px solid var(--rule-2);
      border-radius: var(--radius-sm);
      padding: 3px 8px;
      letter-spacing: 0;
      background: transparent;
    }
    .priority-list {
      list-style: none; margin: 0; padding: 0;
      display: flex; flex-direction: column; gap: 10px;
      counter-reset: priority;
    }
    .priority-list li {
      font-size: 14px;
      color: var(--ink-2);
      line-height: 1.55;
      padding-left: 28px;
      position: relative;
      counter-increment: priority;
    }
    .priority-list li::before {
      content: counter(priority, decimal-leading-zero);
      position: absolute; left: 0; top: 0;
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--muted-2);
      letter-spacing: 0;
    }

    .insight-strip.insight-critical { border-top-color: var(--accent-risk); }
    .insight-strip.insight-warn     { border-top-color: var(--accent-warn); }
    .insight-strip.insight-ok       { border-top-color: var(--accent-ok); }

    /* ---------------- CHARTS ---------------- */

    .charts {
      display: grid;
      grid-template-columns: repeat(12, minmax(0, 1fr));
      gap: 32px;
    }
    .chart-card {
      grid-column: span 6;
      background: var(--surface-2);
      border: 1px solid var(--rule-2);
      padding: 24px 24px 20px;
      display: flex; flex-direction: column; gap: 14px;
      min-width: 0;
    }
    .chart-card-wide { grid-column: span 12; }
    .chart-card-secondary-wide { grid-column: span 12; }

    .chart-head { display: flex; flex-direction: column; gap: 4px; }
    .chart-kicker {
      font-family: var(--font-sans);
      font-size: 10px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--muted-2);
      font-weight: 500;
    }
    .chart-head h3 {
      font-family: var(--font-display);
      font-weight: 500;
      font-size: 20px;
      line-height: 1.2;
      letter-spacing: -0.015em;
      color: var(--ink);
      margin: 0;
    }
    .chart-head p {
      font-size: 13px;
      color: var(--muted);
      margin: 0;
      line-height: 1.5;
    }
    .chart-answer {
      font-family: var(--font-sans);
      font-size: 13px;
      line-height: 1.55;
      color: var(--ink-2);
      margin: 0;
      padding: 10px 0;
      border-top: 1px solid var(--rule);
      border-bottom: 1px solid var(--rule);
    }

    .chart-wrap {
      position: relative;
      width: 100%;
      height: 280px;
      min-height: 280px;
    }
    .chart-card-wide .chart-wrap { height: 300px; min-height: 300px; }

    .chart-data summary {
      font-family: var(--font-sans);
      font-size: 11px;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      color: var(--muted);
      cursor: pointer;
      padding: 6px 0;
      list-style: none;
      border-top: 1px solid var(--rule);
    }
    .chart-data summary::after {
      content: \"view\";
      float: right;
      color: var(--muted-2);
    }
    .chart-data[open] summary::after { content: \"hide\"; }
    .chart-data > div {
      padding-top: 8px;
    }
    .chart-data table {
      width: 100%; border-collapse: collapse;
      font-family: var(--font-mono);
      font-size: 11.5px;
    }
    .chart-data th, .chart-data td {
      padding: 4px 8px 4px 0; text-align: left;
      border-bottom: 1px solid var(--rule);
      color: var(--ink-2);
    }
    .chart-data th {
      color: var(--muted-2);
      font-weight: 500;
      letter-spacing: 0;
      text-transform: none;
      font-size: 10.5px;
    }

    /* ---------------- TABLE ---------------- */

    .table-panel { display: flex; flex-direction: column; gap: 20px; }
    .table-head {
      display: flex; align-items: end; justify-content: space-between;
      gap: 24px; flex-wrap: wrap;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--rule-2);
    }
    .table-head-copy { display: flex; flex-direction: column; gap: 6px; }
    .table-head h3 {
      font-family: var(--font-display);
      font-weight: 500;
      font-size: clamp(24px, 2.6vw, 32px);
      line-height: 1.1;
      letter-spacing: -0.02em;
      color: var(--ink);
      margin: 0;
    }
    .table-head p {
      font-size: 14px; color: var(--muted);
      max-width: 56ch; margin: 0;
    }

    .table-toolbar {
      display: flex; align-items: center; gap: 24px;
    }
    .table-stat {
      display: flex; flex-direction: column; gap: 2px;
      align-items: flex-end;
    }
    .table-stat-label {
      font-family: var(--font-sans);
      font-size: 10px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      color: var(--muted-2);
      font-weight: 500;
    }
    .table-stat strong {
      font-family: var(--font-display);
      font-weight: 500;
      font-size: 20px;
      line-height: 1;
      color: var(--ink);
      font-variant-numeric: tabular-nums;
    }
    .sort-note {
      font-family: var(--font-mono);
      font-size: 11px;
      color: var(--muted-2);
      margin: 0;
    }

    .table-wrap {
      overflow: auto;
      max-height: 640px;
      border: 1px solid var(--rule-2);
      background: var(--surface-2);
    }
    #riskTable {
      width: 100%;
      border-collapse: collapse;
      font-size: 13px;
    }
    #riskTable thead {
      position: sticky; top: 0; z-index: 1;
      background: var(--surface-2);
      border-bottom: 1px solid var(--rule-2);
    }
    #riskTable th {
      text-align: left;
      padding: 12px 14px;
      font-family: var(--font-sans);
      font-size: 10px;
      letter-spacing: 0.14em;
      text-transform: uppercase;
      font-weight: 500;
      color: var(--muted);
      border-bottom: 1px solid var(--rule-2);
      white-space: nowrap;
    }
    #riskTable th.rank-col { padding-right: 4px; }

    .sort-button {
      background: none; border: none; padding: 0;
      font: inherit; color: inherit; letter-spacing: inherit;
      text-transform: inherit; cursor: pointer;
      display: inline-flex; align-items: center; gap: 4px;
    }
    .sort-button:hover { color: var(--ink); }
    .sort-button:focus-visible { outline: none; box-shadow: var(--focus-ring); }
    [aria-sort=\"ascending\"] .sort-button::after  { content: \"↑\"; color: var(--ink); }
    [aria-sort=\"descending\"] .sort-button::after { content: \"↓\"; color: var(--ink); }

    #riskTable td {
      padding: 12px 14px;
      border-bottom: 1px solid var(--rule);
      color: var(--ink-2);
      vertical-align: top;
    }
    #riskTable tbody tr:hover { background: var(--row-hover); }
    #riskTable tbody tr:nth-child(2n) { background: var(--row-alt); }
    #riskTable td.rank-col {
      font-family: var(--font-mono);
      font-size: 11.5px;
      color: var(--muted-2);
      padding-right: 4px;
    }
    #riskTable td.num,
    #riskTable .num {
      font-family: var(--font-mono);
      font-variant-numeric: tabular-nums;
      font-size: 12.5px;
    }

    .tier-tag, .tier-chip {
      display: inline-block;
      font-family: var(--font-sans);
      font-size: 10.5px;
      letter-spacing: 0.10em;
      text-transform: uppercase;
      font-weight: 500;
      padding: 2px 8px;
      border: 1px solid currentColor;
      border-radius: var(--radius-sm);
    }
    .tier-tag.tier-critical, .tier-chip.tier-critical { color: var(--accent-risk); }
    .tier-tag.tier-high, .tier-chip.tier-high     { color: var(--accent-warn); }
    .tier-tag.tier-medium, .tier-chip.tier-medium   { color: var(--muted); }
    .tier-tag.tier-low, .tier-chip.tier-low      { color: var(--accent-ok); }

    /* ---------------- FOOTER SPACING ---------------- */

    .page > *:last-child { margin-bottom: 0; }

    /* ---------------- RESPONSIVE ---------------- */

    @media (max-width: 960px) {
      .page { padding: 32px 20px 64px; gap: 40px; }
      .filters { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .kpi {
        border-right: none; padding-right: 0; padding-left: 0;
        border-bottom: 1px solid var(--rule); padding-bottom: 24px;
      }
      .kpi:nth-child(odd) { border-right: 1px solid var(--rule); padding-right: 20px; }
      .kpi:nth-child(even) { padding-left: 20px; }
      .kpis > .kpi:nth-last-child(-n+2) { border-bottom: none; padding-bottom: 0; }
      .chart-card { grid-column: span 12; }
      .insight-layout { grid-template-columns: 1fr; gap: 32px; }
      .decision-grid { grid-template-columns: 1fr; }
      .decision-card {
        border-right: none;
        border-bottom: 1px solid var(--rule);
        padding-left: 0 !important;
        padding-right: 0;
      }
      .decision-card:last-child { border-bottom: none; }
    }

    @media (max-width: 560px) {
      .filters { grid-template-columns: 1fr; }
      .hero h1 { font-size: 40px; }
      .kpis { grid-template-columns: 1fr; }
      .kpi { border-right: none !important; padding: 24px 0 !important; }
      .kpi:not(:last-child) { border-bottom: 1px solid var(--rule); }
    }

    /* ---------------- PRINT ---------------- */

    @media print {
      :root {
        --paper: #ffffff; --surface: #ffffff; --surface-2: #ffffff;
        --ink: #1a1a1a; --muted: #4a4a4a;
        --shadow: none;
      }
      body { background: #ffffff !important; color: #1a1a1a !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      .page { max-width: none; padding: 12mm 14mm; gap: 28px; }
      .theme-toggle, .print-btn, .reset-btn, .filters, .hero-actions { display: none !important; }
      .chart-card, .table-panel { break-inside: avoid; page-break-inside: avoid; border-color: var(--rule-2); }
      .chart-wrap { height: 220px; min-height: 220px; }
      .table-wrap { max-height: none; overflow: visible; }
    }
  </style>

</head>
<body>
<a class=\"skip-link\" href=\"#mainContent\">Skip to dashboard content</a>
<main class=\"page\" id=\"mainContent\">
  <section class=\"hero\">
    <div class=\"hero-grid\">
      <div class=\"hero-copy\">
        <div class=\"hero-top\">
          <h1>Pricing Discipline Command Center</h1>
          <div class=\"hero-actions\">
            <button id=\"themeToggle\" class=\"theme-toggle\" type=\"button\" aria-label=\"Toggle color mode\">Dark Mode</button>
            <button id=\"printBtn\" class=\"print-btn\" type=\"button\" aria-label=\"Print dashboard\">Print</button>
          </div>
        </div>
        <p class=\"hero-subtitle\">Decision-first view of discount leakage, margin exposure, accountable drivers, and customer-level interventions.</p>
        <p class=\"hero-callout\" id=\"heroCallout\">Assessing the current pricing posture and preparing the clearest intervention view for the selected scope.</p>
        <div class=\"decision-grid\" aria-label=\"Immediate decision summary\">
          <article class=\"decision-card\">
            <span class=\"decision-label\">What matters</span>
            <strong class=\"decision-value\" id=\"decisionMatter\">-</strong>
            <span class=\"decision-note\" id=\"decisionMatterNote\">Largest exposed value in scope</span>
          </article>
          <article class=\"decision-card\">
            <span class=\"decision-label\">What is critical</span>
            <strong class=\"decision-value\" id=\"decisionCritical\">-</strong>
            <span class=\"decision-note\" id=\"decisionCriticalNote\">Primary governance breach</span>
          </article>
          <article class=\"decision-card\">
            <span class=\"decision-label\">Action required</span>
            <strong class=\"decision-value\" id=\"decisionAction\">-</strong>
            <span class=\"decision-note\" id=\"decisionActionNote\">Next commercial operating move</span>
          </article>
        </div>
        <ul class=\"hero-meta\">
          <li id=\"coverageMeta\"></li>
          <li>Synthetic data only</li>
          <li>Decision-support heuristic, not causal attribution</li>
        </ul>
      </div>
      <aside class=\"hero-rail\">
        <article class=\"hero-status hero-status-ok\" id=\"heroStatusCard\">
          <span class=\"hero-status-label\">Decision posture</span>
          <strong class=\"hero-status-value\" id=\"heroStatusValue\">Assessing...</strong>
          <span class=\"hero-status-note\" id=\"heroStatusNote\">Loading governed pricing signals.</span>
        </article>
        <div class=\"hero-summary-grid\">
          <article class=\"summary-card\">
            <span class=\"summary-label\">Margin exposure</span>
            <strong class=\"summary-value\" id=\"heroMarginShare\">-</strong>
            <span class=\"summary-note\">Share of in-scope revenue at risk</span>
          </article>
          <article class=\"summary-card\">
            <span class=\"summary-label\">High-risk accounts</span>
            <strong class=\"summary-value\" id=\"heroHighRisk\">-</strong>
            <span class=\"summary-note\">Critical and high tiers in view</span>
          </article>
          <article class=\"summary-card\">
            <span class=\"summary-label\">Primary bottleneck</span>
            <strong class=\"summary-value\" id=\"heroTopDriver\">-</strong>
            <span class=\"summary-note\">Largest source of risk concentration</span>
          </article>
          <article class=\"summary-card\">
            <span class=\"summary-label\">Current period</span>
            <strong class=\"summary-value\" id=\"heroCurrentView\">-</strong>
            <span class=\"summary-note\">Active time window in scope</span>
          </article>
        </div>
      </aside>
    </div>
  </section>
  <section class=\"panel filters-panel\" aria-labelledby=\"scopeControlsTitle\">
    <div class=\"filters-head\">
      <div class=\"filters-head-copy\">
        <span class=\"section-kicker\">Decision scope</span>
        <h2 id=\"scopeControlsTitle\">Scope Controls</h2>
        <p>Every metric, chart, and queue below uses the same period and commercial slice.</p>
      </div>
      <button id=\"resetFiltersBtn\" class=\"reset-btn\" type=\"button\" aria-label=\"Reset filters\">Reset Filters</button>
    </div>
    <div class=\"controls-row\">
      <p class=\"controls-meta\" id=\"controlsMeta\">Scope: all segments, regions, categories, and channels.</p>
    </div>
    <div class=\"filters\">
      <div class=\"field\"><label for=\"periodStartFilter\">Start Month</label><select id=\"periodStartFilter\"></select></div>
      <div class=\"field\"><label for=\"periodEndFilter\">End Month</label><select id=\"periodEndFilter\"></select></div>
      <div class=\"field\"><label for=\"segmentFilter\">Segment</label><select id=\"segmentFilter\"></select></div>
      <div class=\"field\"><label for=\"regionFilter\">Region</label><select id=\"regionFilter\"></select></div>
      <div class=\"field\"><label for=\"categoryFilter\">Product Category</label><select id=\"categoryFilter\"></select></div>
      <div class=\"field\"><label for=\"channelFilter\">Sales Channel</label><select id=\"channelFilter\"></select></div>
    </div>
  </section>

  <div class=\"section-head\">
    <div class=\"section-head-copy\">
      <span class=\"section-kicker\">Commercial posture</span>
      <h2>Decision KPIs</h2>
    </div>
    <p>Each KPI states the interpretation and the operating threshold it is judged against.</p>
  </div>
  <section class=\"kpis\">
    <article class=\"kpi kpi-neutral\" id=\"kpiRevenueCard\">
      <div class=\"kpi-head\">
        <p class=\"kpi-title\">Revenue Governed</p>
        <span class=\"kpi-state kpi-state-neutral\" id=\"kpiRevenueState\">Scope</span>
      </div>
      <p class=\"kpi-value\" id=\"kpiRevenue\">-</p>
      <p class=\"kpi-sub\">Commercial value governed by current filters</p>
      <p class=\"kpi-detail\" id=\"kpiRevenueDetail\">Share of revenue under the current scope.</p>
    </article>
    <article class=\"kpi kpi-warn\" id=\"kpiDiscountCard\">
      <div class=\"kpi-head\">
        <p class=\"kpi-title\">Weighted Discount</p>
        <span class=\"kpi-state kpi-state-warn\" id=\"kpiDiscountState\">Watch</span>
      </div>
      <p class=\"kpi-value\" id=\"kpiDiscount\">-</p>
      <p class=\"kpi-sub\">List-price leakage weighted by revenue</p>
      <p class=\"kpi-detail\" id=\"kpiDiscountDetail\">Monitor against governance thresholds.</p>
    </article>
    <article class=\"kpi kpi-critical\" id=\"kpiMarginRiskCard\">
      <div class=\"kpi-head\">
        <p class=\"kpi-title\">Margin At Risk</p>
        <span class=\"kpi-state kpi-state-critical\" id=\"kpiMarginRiskState\">Risk</span>
      </div>
      <p class=\"kpi-value\" id=\"kpiMarginRisk\">-</p>
      <p class=\"kpi-sub\">High-discount and weak-margin overlap</p>
      <p class=\"kpi-detail\" id=\"kpiMarginRiskDetail\">Exposure share within scoped revenue.</p>
    </article>
    <article class=\"kpi kpi-warn\" id=\"kpiHighRiskCard\">
      <div class=\"kpi-head\">
        <p class=\"kpi-title\">High-Risk Customers</p>
        <span class=\"kpi-state kpi-state-warn\" id=\"kpiHighRiskState\">Watch</span>
      </div>
      <p class=\"kpi-value\" id=\"kpiHighRisk\">-</p>
      <p class=\"kpi-sub\">Accounts needing priority governance</p>
      <p class=\"kpi-detail\" id=\"kpiHighRiskDetail\">Accounts most likely to need intervention now.</p>
    </article>
  </section>

  <section class=\"panel insight-strip\">
    <div class=\"insight-layout\">
      <div class=\"insight-summary\">
        <span class=\"insight-label\">Executive readout</span>
        <p class=\"insight-main\" id=\"insightMain\">Assessing current pricing posture...</p>
        <div class=\"insight-chips\" id=\"insightChips\"></div>
      </div>
      <div class=\"insight-action\">
        <span class=\"insight-label\">Operating priorities</span>
        <ul class=\"priority-list\" id=\"priorityList\">
          <li>Preparing priority sequence for the current scope.</li>
        </ul>
      </div>
    </div>
  </section>

  <div class=\"section-head\">
    <div class=\"section-head-copy\">
      <span class=\"section-kicker\">Risk diagnostics</span>
      <h2>Explanation</h2>
    </div>
    <p>Charts answer the operating questions behind the decision, from momentum to owner workload.</p>
  </div>
  <section class=\"charts\">
    <article class=\"chart-card chart-card-wide chart-card-trend\" aria-labelledby=\"trendChartTitle\">
      <div class=\"chart-head\">
        <span class=\"chart-kicker\">Business question: is discount pressure accelerating?</span>
        <h3 id=\"trendChartTitle\">Weighted Discount Trend</h3>
        <p>Monthly list-price leakage after scope filters.</p>
      </div>
      <p class=\"chart-answer\" id=\"trendChartAnswer\">Loading trend interpretation.</p>
      <div class=\"chart-wrap\"><canvas id=\"trendChart\" aria-label=\"Monthly weighted discount trend\" aria-describedby=\"trendChartAnswer trendChartData\"></canvas></div>
      <details class=\"chart-data\"><summary>View chart data</summary><div id=\"trendChartData\"></div></details>
    </article>

    <article class=\"chart-card chart-card-segment\" aria-labelledby=\"segmentChartTitle\">
      <div class=\"chart-head\">
        <span class=\"chart-kicker\">Business question: which segment breaks policy first?</span>
        <h3 id=\"segmentChartTitle\">Discount Concentration by Segment</h3>
        <p>Segments ranked by revenue-weighted discount.</p>
      </div>
      <p class=\"chart-answer\" id=\"segmentChartAnswer\">Loading segment interpretation.</p>
      <div class=\"chart-wrap\"><canvas id=\"segmentChart\" aria-label=\"Weighted discount by segment\" aria-describedby=\"segmentChartAnswer segmentChartData\"></canvas></div>
      <details class=\"chart-data\"><summary>View chart data</summary><div id=\"segmentChartData\"></div></details>
    </article>

    <article class=\"chart-card chart-card-region\" aria-labelledby=\"regionRiskChartTitle\">
      <div class=\"chart-head\">
        <span class=\"chart-kicker\">Business question: where is the operational exposure?</span>
        <h3 id=\"regionRiskChartTitle\">Margin Exposure by Region</h3>
        <p>Revenue value caught in high-discount and weak-margin overlap.</p>
      </div>
      <p class=\"chart-answer\" id=\"regionRiskChartAnswer\">Loading regional exposure interpretation.</p>
      <div class=\"chart-wrap\"><canvas id=\"regionRiskChart\" aria-label=\"Margin exposure by region\" aria-describedby=\"regionRiskChartAnswer regionRiskChartData\"></canvas></div>
      <details class=\"chart-data\"><summary>View chart data</summary><div id=\"regionRiskChartData\"></div></details>
    </article>

    <article class=\"chart-card chart-card-secondary-wide chart-card-action\" aria-labelledby=\"actionChartTitle\">
      <div class=\"chart-head\">
        <span class=\"chart-kicker\">Business question: what work should governance do first?</span>
        <h3 id=\"actionChartTitle\">Intervention Workload by Revenue</h3>
        <p>Customer revenue grouped by recommended commercial action.</p>
      </div>
      <p class=\"chart-answer\" id=\"actionChartAnswer\">Loading action mix interpretation.</p>
      <div class=\"chart-wrap\"><canvas id=\"actionChart\" aria-label=\"Revenue by recommended intervention action\" aria-describedby=\"actionChartAnswer actionChartData\"></canvas></div>
      <details class=\"chart-data\"><summary>View chart data</summary><div id=\"actionChartData\"></div></details>
    </article>
  </section>

  <section class=\"table-panel\">
    <div class=\"table-head\">
      <div class=\"table-head-copy\">
        <span class=\"section-kicker\">Operational detail</span>
        <h3>Customer Review Queue</h3>
        <p>Sequenced accounts with revenue, discount evidence, risk driver, and the recommended operating action.</p>
      </div>
      <div class=\"table-toolbar\">
        <div class=\"table-stat\">
          <span class=\"table-stat-label\">Displayed</span>
          <strong id=\"tableCount\">-</strong>
        </div>
        <p class=\"sort-note\" id=\"tableSortMeta\" aria-live=\"polite\">Sorted by priority score.</p>
      </div>
    </div>
    <div class=\"table-wrap\">
      <table id=\"riskTable\">
        <thead>
          <tr>
            <th class=\"rank-col\" scope=\"col\">#</th>
            <th scope=\"col\" aria-sort=\"none\"><button type=\"button\" class=\"sort-button\" data-key=\"customer_id\">Customer</button></th>
            <th scope=\"col\" aria-sort=\"none\"><button type=\"button\" class=\"sort-button\" data-key=\"segment\">Segment</button></th>
            <th scope=\"col\" aria-sort=\"none\"><button type=\"button\" class=\"sort-button\" data-key=\"region\">Region</button></th>
            <th scope=\"col\" aria-sort=\"none\"><button type=\"button\" class=\"sort-button\" data-key=\"filtered_revenue\">Revenue</button></th>
            <th scope=\"col\" aria-sort=\"none\"><button type=\"button\" class=\"sort-button\" data-key=\"filtered_avg_discount\">Avg Discount</button></th>
            <th scope=\"col\" aria-sort=\"descending\"><button type=\"button\" class=\"sort-button\" data-key=\"governance_priority_score\">Score</button></th>
            <th scope=\"col\" aria-sort=\"none\"><button type=\"button\" class=\"sort-button\" data-key=\"risk_tier\">Risk Tier</button></th>
            <th scope=\"col\" aria-sort=\"none\"><button type=\"button\" class=\"sort-button\" data-key=\"main_risk_driver\">Risk Driver</button></th>
            <th scope=\"col\" aria-sort=\"none\"><button type=\"button\" class=\"sort-button\" data-key=\"recommended_action\">Recommended Action</button></th>
          </tr>
        </thead>
        <tbody></tbody>
      </table>
    </div>
  </section>

</main>

<script>
const DATA = __DATA_JSON__;
const ALL = "__ALL_VALUE__";
const THEME_STORAGE_KEY = 'pricing_dashboard_theme';
const POLICY = DATA.policy || {};
const KPI_POLICY = POLICY.kpi_card_thresholds || {};
const POSTURE_POLICY = POLICY.posture_thresholds || {};

Chart.defaults.font.family = '"IBM Plex Sans", -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial, sans-serif';
Chart.defaults.font.size = 11.5;
Chart.defaults.color = '#6c655e';
Chart.defaults.borderColor = 'rgba(26,26,26,0.08)';
Chart.defaults.plugins.legend.labels.usePointStyle = true;
Chart.defaults.plugins.legend.labels.boxWidth = 8;
Chart.defaults.plugins.legend.labels.boxHeight = 8;
Chart.defaults.plugins.legend.labels.padding = 14;
Chart.defaults.plugins.tooltip.backgroundColor = '#1a1a1a';
Chart.defaults.plugins.tooltip.titleFont = { family: '"IBM Plex Sans", sans-serif', size: 11, weight: '500' };
Chart.defaults.plugins.tooltip.bodyFont = { family: '"IBM Plex Mono", monospace', size: 11 };
Chart.defaults.plugins.tooltip.padding = 10;
Chart.defaults.plugins.tooltip.cornerRadius = 2;
Chart.defaults.plugins.tooltip.displayColors = false;
Chart.defaults.borderRadius = 0;

const filterEls = {
  segment: document.getElementById('segmentFilter'),
  region: document.getElementById('regionFilter'),
  category: document.getElementById('categoryFilter'),
  sales_channel: document.getElementById('channelFilter'),
  period_start: document.getElementById('periodStartFilter'),
  period_end: document.getElementById('periodEndFilter')
};
const themeToggleEl = document.getElementById('themeToggle');
const printBtnEl = document.getElementById('printBtn');
const resetFiltersBtnEl = document.getElementById('resetFiltersBtn');

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

function stateClass(level) {
  if (level === 'critical') return 'kpi-state kpi-state-critical';
  if (level === 'warn') return 'kpi-state kpi-state-warn';
  if (level === 'ok') return 'kpi-state kpi-state-ok';
  return 'kpi-state kpi-state-neutral';
}

function applyStateTag(id, level, label) {
  const el = document.getElementById(id);
  if (!el) return;
  el.className = stateClass(level);
  el.textContent = label;
}

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

function tooltipPct(context) {
  return `${context.dataset.label}: ${Number(context.parsed.y ?? context.parsed.x ?? 0).toFixed(1)}%`;
}

function tooltipCurrency(context) {
  const parsed = Number(context.parsed.x ?? context.parsed.y ?? 0);
  return `${context.dataset.label}: ${fmtCurrency(parsed)}`;
}

function updateThemeToggleLabel(theme) {
  if (!themeToggleEl) return;
  themeToggleEl.textContent = theme === 'dark' ? 'Light Mode' : 'Dark Mode';
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

function titleCaseLabel(value) {
  return String(value || '')
    .replaceAll('_', ' ')
    .replace(/\\b\\w/g, (match) => match.toUpperCase());
}

function scoreComponentLabel(value) {
  const labels = {
    pricing_risk_score: 'Price Variance',
    discount_dependency_score: 'Discount Dependency',
    margin_erosion_score: 'Margin Erosion'
  };
  return labels[value] || titleCaseLabel(value);
}

function thresholdGapLabel(value, warnThreshold) {
  const diffPts = ((Number(value) || 0) - Number(warnThreshold || 0)) * 100;
  if (Math.abs(diffPts) < 0.05) return 'At the warning threshold';
  return diffPts > 0
    ? `${diffPts.toFixed(1)} pts above warning`
    : `${Math.abs(diffPts).toFixed(1)} pts below warning`;
}

function topEntry(map) {
  return [...map.entries()].sort((a, b) => Number(b[1]) - Number(a[1]))[0] || [null, 0];
}

function setText(id, value) {
  const el = document.getElementById(id);
  if (el) el.textContent = value;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;')
    .replaceAll("'", '&#39;');
}

function populateSelect(el, values) {
  const isMonth = el.id === 'periodStartFilter' || el.id === 'periodEndFilter';
  el.innerHTML = values
    .map((v) => `<option value=\"${escapeHtml(v)}\">${escapeHtml(isMonth ? fmtMonth(v) : v)}</option>`)
    .join('');
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

function renderChartDataTable(containerId, rows, columns) {
  const container = document.getElementById(containerId);
  if (!container) return;
  if (!rows.length) {
    container.innerHTML = '<p class="chart-answer">No data available for the current scope.</p>';
    return;
  }
  const header = columns.map((col) => `<th scope="col">${escapeHtml(col.label)}</th>`).join('');
  const body = rows.slice(0, 12).map((row) => {
    const cells = columns.map((col) => {
      const value = col.format ? col.format(row[col.key]) : row[col.key];
      return `<td>${escapeHtml(value)}</td>`;
    }).join('');
    return `<tr>${cells}</tr>`;
  }).join('');
  container.innerHTML = `<table><thead><tr>${header}</tr></thead><tbody>${body}</tbody></table>`;
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

function resolvePosture(kpi) {
  const discountWarn = Number(POSTURE_POLICY.weighted_discount_warn ?? 0.14);
  const discountCritical = Number(POSTURE_POLICY.weighted_discount_critical ?? 0.20);
  const marginWarn = Number(POSTURE_POLICY.margin_risk_share_warn ?? 0.12);
  const marginCritical = Number(POSTURE_POLICY.margin_risk_share_critical ?? 0.20);
  const riskWarn = Number(POSTURE_POLICY.high_risk_count_warn ?? 35);
  const riskCritical = Number(POSTURE_POLICY.high_risk_count_critical ?? 80);

  if (
    Number(kpi.weighted_discount_pct || 0) >= discountCritical ||
    Number(kpi.margin_risk_share || 0) >= marginCritical ||
    Number(kpi.high_risk_count || 0) >= riskCritical
  ) {
    return {
      level: 'critical',
      label: 'Intervene now',
      narrative: 'Current scope shows concentrated discount-led risk and should move into immediate commercial governance action.'
    };
  }

  if (
    Number(kpi.weighted_discount_pct || 0) >= discountWarn ||
    Number(kpi.margin_risk_share || 0) >= marginWarn ||
    Number(kpi.high_risk_count || 0) >= riskWarn
  ) {
    return {
      level: 'warn',
      label: 'Tight watch',
      narrative: 'Current scope is mixed. Targeted intervention is recommended before margin risk concentration broadens.'
    };
  }

  return {
    level: 'ok',
    label: 'Controlled',
    narrative: 'Current scope remains within monitor range and does not yet indicate broad intervention pressure.'
  };
}

function updateKpis(filters, riskRows) {
  const kpi = aggregateScopedPricing(filters);
  const marginRiskShare = (Number(kpi.net_revenue) || 0) > 0 ? (Number(kpi.margin_at_risk) || 0) / Number(kpi.net_revenue) : 0;
  const totalPeriodKpi = aggregateScopedPricing({
    ...filters,
    segment: ALL,
    region: ALL,
    category: ALL,
    sales_channel: ALL
  });
  const revenueShare = Number(totalPeriodKpi.net_revenue) > 0 ? Number(kpi.net_revenue || 0) / Number(totalPeriodKpi.net_revenue) : 0;

  document.getElementById('kpiRevenue').textContent = fmtCurrency(Number(kpi.net_revenue) || 0);
  document.getElementById('kpiDiscount').textContent = fmtPct(Number(kpi.weighted_discount_pct) || 0);
  document.getElementById('kpiMarginRisk').textContent = fmtCurrency(Number(kpi.margin_at_risk) || 0);

  const highRiskCount = riskRows.filter((r) => r.risk_tier === 'High' || r.risk_tier === 'Critical').length;
  document.getElementById('kpiHighRisk').textContent = highRiskCount.toLocaleString('en-US');

  const discountCard = document.getElementById('kpiDiscountCard');
  const discountWarn = Number(KPI_POLICY.weighted_discount_warn ?? 0.14);
  const discountCritical = Number(KPI_POLICY.weighted_discount_critical ?? 0.20);
  const marginWarn = Number(KPI_POLICY.margin_risk_share_warn ?? 0.12);
  const marginCritical = Number(KPI_POLICY.margin_risk_share_critical ?? 0.20);
  const riskWarn = Number(KPI_POLICY.high_risk_count_warn ?? 35);
  const riskCritical = Number(KPI_POLICY.high_risk_count_critical ?? 80);

  const discountLevel = kpi.weighted_discount_pct >= discountCritical ? 'critical' : kpi.weighted_discount_pct >= discountWarn ? 'warn' : 'ok';
  discountCard.className = `kpi ${discountLevel === 'critical' ? 'kpi-critical' : discountLevel === 'warn' ? 'kpi-warn' : 'kpi-ok'}`;
  applyStateTag('kpiDiscountState', discountLevel, discountLevel === 'critical' ? 'Critical' : discountLevel === 'warn' ? 'Watch' : 'Stable');

  const marginCard = document.getElementById('kpiMarginRiskCard');
  const marginLevel = marginRiskShare >= marginCritical ? 'critical' : marginRiskShare >= marginWarn ? 'warn' : 'ok';
  marginCard.className = `kpi ${marginLevel === 'critical' ? 'kpi-critical' : marginLevel === 'warn' ? 'kpi-warn' : 'kpi-ok'}`;
  applyStateTag('kpiMarginRiskState', marginLevel, marginLevel === 'critical' ? 'Critical' : marginLevel === 'warn' ? 'Watch' : 'Stable');

  const highRiskCard = document.getElementById('kpiHighRiskCard');
  const riskLevel = highRiskCount >= riskCritical ? 'critical' : highRiskCount >= riskWarn ? 'warn' : 'ok';
  highRiskCard.className = `kpi ${riskLevel === 'critical' ? 'kpi-critical' : riskLevel === 'warn' ? 'kpi-warn' : 'kpi-ok'}`;
  applyStateTag('kpiHighRiskState', riskLevel, riskLevel === 'critical' ? 'Critical' : riskLevel === 'warn' ? 'Watch' : 'Stable');
  applyStateTag('kpiRevenueState', 'neutral', 'Scope');

  document.getElementById('kpiRevenueDetail').textContent = `${fmtPct(revenueShare || 0)} of the selected period revenue is currently in view.`;
  document.getElementById('kpiDiscountDetail').textContent = `${thresholdGapLabel(kpi.weighted_discount_pct, discountWarn)} against the governance warning threshold.`;
  document.getElementById('kpiMarginRiskDetail').textContent = `${fmtPct(marginRiskShare || 0)} of scoped revenue is exposed to the margin-at-risk proxy.`;
  document.getElementById('kpiHighRiskDetail').textContent = `${highRiskCount.toLocaleString('en-US')} accounts currently require high-priority monitoring or action.`;

  return { ...kpi, high_risk_count: highRiskCount, margin_risk_share: marginRiskShare };
}

function updateInsight(filters, kpi, riskRows) {
  const topDriverMap = new Map();
  const topActionMap = new Map();
  riskRows.forEach((r) => {
    const d = r.main_risk_driver || 'unknown';
    topDriverMap.set(d, (topDriverMap.get(d) || 0) + (Number(r.filtered_revenue) || 0));
    const action = r.recommended_action || 'unclassified';
    topActionMap.set(action, (topActionMap.get(action) || 0) + (Number(r.filtered_revenue) || 0));
  });
  const [topDriver, topDriverRevenue] = topEntry(topDriverMap);
  const [topAction, topActionRevenue] = topEntry(topActionMap);
  const topDriverLabel = scoreComponentLabel(topDriver || 'mixed');
  const topActionLabel = topAction ? titleCaseLabel(topAction) : 'Monitor Only';

  const posture = resolvePosture(kpi);
  document.getElementById('insightMain').textContent = posture.narrative;
  const insightEl = document.querySelector('.insight-strip');
  if (insightEl) {
    insightEl.className = `panel insight-strip insight-${posture.level}`;
  }

  let actionText = `Maintain current cadence and keep ${topDriverLabel.toLowerCase()} under watch as the main residual source of exposure.`;
  if (posture.level === 'critical') {
    actionText = `Prioritize immediate review of ${topDriverLabel.toLowerCase()} exposures and the highest-revenue accounts in the queue.`;
  } else if (posture.level === 'warn') {
    actionText = `Run a targeted governance pass on ${topDriverLabel.toLowerCase()} exposures and watch for near-term acceleration.`;
  }

  const priorityItems = [
    `${topActionLabel} first: ${fmtCurrency(Number(topActionRevenue) || 0)} of reviewed revenue sits behind this action.`,
    `Start with the top customer queue; it is already sorted by governance score and filtered revenue.`,
    `Use ${topDriverLabel.toLowerCase()} as the operating owner for root-cause review.`
  ];
  document.getElementById('priorityList').innerHTML = priorityItems.map((item) => `<li>${escapeHtml(item)}</li>`).join('');

  const chips = [
    `Scope: ${filters.segment === ALL ? 'All segments' : filters.segment}`,
    `Weighted discount: ${fmtPct(kpi.weighted_discount_pct || 0)}`,
    `Margin at risk share: ${fmtPct(kpi.margin_risk_share || 0)}`,
    `High-risk customers: ${(kpi.high_risk_count || 0).toLocaleString('en-US')}`,
    `Top risk driver: ${topDriverLabel}`
  ];
  document.getElementById('insightChips').innerHTML = chips.map((c) => `<span class="insight-chip">${c}</span>`).join('');

  const heroStatusCard = document.getElementById('heroStatusCard');
  if (heroStatusCard) {
    heroStatusCard.className = `hero-status hero-status-${posture.level}`;
  }
  document.getElementById('heroStatusValue').textContent = posture.label;
  document.getElementById('heroStatusNote').textContent = actionText;
  document.getElementById('heroCallout').textContent = `${posture.narrative} ${fmtPct(kpi.margin_risk_share || 0)} of in-scope revenue is currently exposed to the margin-at-risk proxy, with ${topDriverLabel.toLowerCase()} as the main driver.`;
  setText('heroMarginShare', fmtPct(kpi.margin_risk_share || 0));
  setText('heroHighRisk', (kpi.high_risk_count || 0).toLocaleString('en-US'));
  setText('heroTopDriver', topDriverLabel);
  setText('heroCurrentView', `${fmtMonth(filters.period_start)} - ${fmtMonth(filters.period_end)}`);
  setText('decisionMatter', fmtCurrency(Number(kpi.margin_at_risk) || 0));
  setText('decisionMatterNote', `${fmtPct(kpi.margin_risk_share || 0)} of scoped revenue is exposed`);
  setText('decisionCritical', topDriverLabel);
  setText('decisionCriticalNote', `${fmtCurrency(Number(topDriverRevenue) || 0)} concentrated in this driver`);
  setText('decisionAction', topActionLabel);
  setText('decisionActionNote', `${fmtCurrency(Number(topActionRevenue) || 0)} affected revenue`);
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

  if (monthly.length === 0) {
    setText('trendChartAnswer', 'No priced revenue is available for the selected scope.');
  } else if (monthly.length === 1) {
    setText('trendChartAnswer', `Current month weighted discount is ${fmtPct(monthly[0].weighted_discount_pct)}.`);
  } else {
    const latest = monthly[monthly.length - 1];
    const prior = monthly[monthly.length - 2];
    const deltaPts = (latest.weighted_discount_pct - prior.weighted_discount_pct) * 100;
    const direction = deltaPts >= 0 ? 'up' : 'down';
    setText('trendChartAnswer', `${fmtMonth(latest.month)} is ${fmtPct(latest.weighted_discount_pct)} (${direction} ${Math.abs(deltaPts).toFixed(1)} pts vs prior month).`);
  }
  renderChartDataTable('trendChartData', monthly, [
    { key: 'month', label: 'Month', format: fmtMonth },
    { key: 'weighted_discount_pct', label: 'Weighted discount', format: (v) => fmtPct(Number(v) || 0) }
  ]);

  makeOrUpdateChart('trendChart', {
    type: 'line',
    data: {
      labels: monthly.map((r) => fmtMonth(r.month)),
      datasets: [{
        label: 'Weighted discount (%)',
        data: monthly.map((r) => r.weighted_discount_pct * 100),
        borderColor: palette.trendLine,
        backgroundColor: palette.trendFill,
        pointRadius: 1.5,
        pointHitRadius: 8,
        borderWidth: 2.2,
        tension: 0.24,
        fill: true
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: tooltipPct
          }
        }
      },
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

  const top = rows[0];
  setText(
    'segmentChartAnswer',
    top
      ? `${top.segment} has the highest weighted discount at ${fmtPct(top.weighted_discount_pct)}.`
      : 'No segment has priced revenue in the selected scope.'
  );
  renderChartDataTable('segmentChartData', rows, [
    { key: 'segment', label: 'Segment' },
    { key: 'weighted_discount_pct', label: 'Weighted discount', format: (v) => fmtPct(Number(v) || 0) }
  ]);

  makeOrUpdateChart('segmentChart', {
    type: 'bar',
    data: {
      labels: rows.map((r) => r.segment),
      datasets: [{
        label: 'Weighted discount (%)',
        data: rows.map((r) => (Number(r.weighted_discount_pct) || 0) * 100),
        backgroundColor: palette.segment,
        borderRadius: 6,
        borderSkipped: false,
        maxBarThickness: 54
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: tooltipPct
          }
        }
      },
      scales: {
        x: {
          ticks: {
            color: palette.axisText,
            minRotation: rows.length > 5 ? 20 : 0,
            maxRotation: rows.length > 5 ? 35 : 0,
            callback: (_, i) => compactLabel(rows[i]?.segment || '', 18)
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

  const top = rows[0];
  setText(
    'regionRiskChartAnswer',
    top
      ? `${top.region} carries the largest exposure at ${fmtCurrency(Number(top.margin_at_risk) || 0)}.`
      : 'No regional margin exposure is available for the selected scope.'
  );
  renderChartDataTable('regionRiskChartData', rows, [
    { key: 'region', label: 'Region' },
    { key: 'margin_at_risk', label: 'Margin at risk', format: (v) => fmtCurrency(Number(v) || 0) }
  ]);

  makeOrUpdateChart('regionRiskChart', {
    type: 'bar',
    data: {
      labels: rows.map((r) => r.region),
      datasets: [{
        label: 'Margin at risk',
        data: rows.map((r) => Number(r.margin_at_risk) || 0),
        backgroundColor: palette.region,
        borderRadius: 6,
        borderSkipped: false,
        maxBarThickness: 54
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: tooltipCurrency
          }
        }
      },
      scales: {
        x: {
          ticks: {
            color: palette.axisText,
            minRotation: rows.length > 5 ? 20 : 0,
            maxRotation: rows.length > 5 ? 35 : 0,
            callback: (_, i) => compactLabel(rows[i]?.region || '', 18)
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

function collapseTail(rows, maxItems = 6, otherLabel = 'Other actions') {
  if (rows.length <= maxItems) return rows;
  const keep = Math.max(1, maxItems - 1);
  const head = rows.slice(0, keep);
  const tailTotal = rows.slice(keep).reduce((acc, row) => acc + (Number(row.value) || 0), 0);
  return [...head, { label: otherLabel, value: tailTotal }];
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
  const displayRows = collapseTail(rows, 6);
  const top = rows[0];

  setText(
    'actionChartAnswer',
    top
      ? `${titleCaseLabel(top.label)} is the largest workload bucket at ${fmtCurrency(Number(top.value) || 0)}.`
      : 'No intervention workload is available for the selected scope.'
  );
  renderChartDataTable('actionChartData', displayRows, [
    { key: 'label', label: 'Recommended action', format: titleCaseLabel },
    { key: 'value', label: 'Revenue in scope', format: (v) => fmtCurrency(Number(v) || 0) }
  ]);

  makeOrUpdateChart('actionChart', {
    type: 'bar',
    data: {
      labels: displayRows.map((r) => compactLabel(r.label, 28)),
      datasets: [{
        label: 'Revenue in scope',
        data: displayRows.map((r) => r.value),
        backgroundColor: palette.action,
        borderRadius: 6,
        borderSkipped: false,
        maxBarThickness: 52
      }]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      indexAxis: 'y',
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: tooltipCurrency
          }
        }
      },
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
  const safeTier = escapeHtml(tier || 'Unknown');
  const cls = {
    Critical: 'tier-chip tier-critical',
    High: 'tier-chip tier-high',
    Medium: 'tier-chip tier-medium',
    Low: 'tier-chip tier-low'
  }[tier] || 'tier-chip';

  return `<span class=\"${cls}\">${safeTier}</span>`;
}

function actionChip(action) {
  return `<span class=\"action-chip\">${escapeHtml(action || 'Unclassified')}</span>`;
}

function sortLabel(key) {
  const labels = {
    customer_id: 'customer',
    segment: 'segment',
    region: 'region',
    filtered_revenue: 'revenue',
    filtered_avg_discount: 'average discount',
    governance_priority_score: 'priority score',
    risk_tier: 'risk tier',
    main_risk_driver: 'risk driver',
    recommended_action: 'recommended action'
  };
  return labels[key] || key;
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

function updateTableSortIndicators() {
  document.querySelectorAll('#riskTable thead th[aria-sort]').forEach((th) => {
    const button = th.querySelector('.sort-button');
    const key = button ? button.getAttribute('data-key') : null;
    th.classList.remove('sort-asc', 'sort-desc');
    if (key === tableState.key) {
      th.classList.add(tableState.dir === 'asc' ? 'sort-asc' : 'sort-desc');
      th.setAttribute('aria-sort', tableState.dir === 'asc' ? 'ascending' : 'descending');
    } else {
      th.setAttribute('aria-sort', 'none');
    }
  });
}

function renderTable(riskRows) {
  const sortedRows = sortRows(riskRows);
  const displayedRows = sortedRows.slice(0, 120);
  const tbody = document.querySelector('#riskTable tbody');
  updateTableSortIndicators();

  const tableCountEl = document.getElementById('tableCount');
  if (tableCountEl) {
    tableCountEl.textContent = `${displayedRows.length} / ${riskRows.length}`;
  }
  const tableSortMetaEl = document.getElementById('tableSortMeta');
  if (tableSortMetaEl) {
    tableSortMetaEl.textContent = `Sorted by ${sortLabel(tableState.key)} (${tableState.dir === 'asc' ? 'ascending' : 'descending'}).`;
  }

  tbody.innerHTML = displayedRows.map((r, index) => `
    <tr>
      <td class="rank-cell">${index + 1}</td>
      <td>${escapeHtml(r.customer_id)}</td>
      <td>${escapeHtml(r.segment)}</td>
      <td>${escapeHtml(r.region)}</td>
      <td>${fmtCurrency(Number(r.filtered_revenue) || 0)}</td>
      <td>${fmtPct(Number(r.filtered_avg_discount) || 0)}</td>
      <td>${(Number(r.governance_priority_score) || 0).toFixed(1)}</td>
      <td>${tierChip(r.risk_tier)}</td>
      <td>${escapeHtml(scoreComponentLabel(r.main_risk_driver))}</td>
      <td class="action-cell">${actionChip(r.recommended_action)}</td>
    </tr>
  `).join('');
}

function initMeta() {
  document.getElementById('coverageMeta').textContent =
    `Commercial window: ${DATA.meta.coverage_start} to ${DATA.meta.coverage_end}`;
}

function setPeriodOptions() {
  const months = DATA.filterOptions.order_month || [];
  populateSelect(filterEls.period_start, months);
  populateSelect(filterEls.period_end, months);

  if (months.length > 0) {
    filterEls.period_start.value = months[0];
    filterEls.period_end.value = months[months.length - 1];
  }
}

function updateSelectedPeriodMeta(filters) {
  document.getElementById('coverageMeta').textContent =
    `Commercial window: ${DATA.meta.coverage_start} to ${DATA.meta.coverage_end} | Current view: ${fmtMonth(filters.period_start)} to ${fmtMonth(filters.period_end)}`;
}

function updateControlsMeta(filters) {
  const readable = (val, label) => val === ALL ? `all ${label}` : val;
  const text = `Scope: ${readable(filters.segment, 'segments')} · ${readable(filters.region, 'regions')} · ${readable(filters.category, 'categories')} · ${readable(filters.sales_channel, 'channels')} · ${fmtMonth(filters.period_start)} to ${fmtMonth(filters.period_end)}.`;
  document.getElementById('controlsMeta').textContent = text;
}

function resetFilters() {
  filterEls.segment.value = ALL;
  filterEls.region.value = ALL;
  filterEls.category.value = ALL;
  filterEls.sales_channel.value = ALL;
  const months = DATA.filterOptions.order_month || [];
  if (months.length > 0) {
    filterEls.period_start.value = months[0];
    filterEls.period_end.value = months[months.length - 1];
  }
  updateAll();
}

function updateAll() {
  const filters = getFilters();
  const riskRows = scopedRiskRows(filters);

  updateSelectedPeriodMeta(filters);
  updateControlsMeta(filters);
  const kpi = updateKpis(filters, riskRows);
  updateInsight(filters, kpi, riskRows);
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
  if (resetFiltersBtnEl) resetFiltersBtnEl.addEventListener('click', resetFilters);

  document.querySelectorAll('#riskTable .sort-button[data-key]').forEach((button) => {
    button.addEventListener('click', () => {
      const key = button.getAttribute('data-key');
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
  if (printBtnEl) {
    printBtnEl.addEventListener('click', () => window.print());
  }

  initMeta();
  updateAll();
}

window.addEventListener('beforeprint', () => {
  Object.values(charts).forEach((chart) => chart.resize());
});

window.addEventListener('afterprint', () => {
  Object.values(charts).forEach((chart) => chart.resize());
});

init();
</script>
</body>
</html>
"""

    html = html.replace("__DATA_JSON__", data_json).replace("__ALL_VALUE__", ALL_VALUE)

    dashboard_filename = "pricing-discipline-command-center.html"
    dashboard_path = dashboard_dir / dashboard_filename
    dashboard_path.write_text(html, encoding="utf-8")

    vendor_source = Path(__file__).resolve().parents[2] / "docs" / "vendor" / "chart.umd.min.js"
    if vendor_source.exists():
        vendor_target = dashboard_dir / "vendor" / "chart.umd.min.js"
        vendor_target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(vendor_source, vendor_target)

    return dashboard_path
