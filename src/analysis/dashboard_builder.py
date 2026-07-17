"""Build the versioned single-file executive dashboard.

Data-shaping helpers produce the KPI, monthly, customer, and risk payloads consumed by
the embedded HTML/CSS/Chart.js template. The builder writes the HTML and local Chart.js
asset under ``dashboard_dir`` and returns the HTML path.
"""

from __future__ import annotations

import json
import shutil
from itertools import combinations
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from src.utils.policy import get_margin_at_risk_proxy_max, load_dashboard_policy

ALL_VALUE = "All"
RISK_EXPORT_TARGET_ROWS = 140


def _as_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = json.loads(df.to_json(orient="records", date_format="iso"))
    return records


def _json_for_script(payload: dict[str, Any]) -> str:
    """Serialize JSON without allowing data to terminate the enclosing script element."""
    raw = json.dumps(payload, separators=(",", ":"))
    return (
        raw.replace("&", "\\u0026")
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


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
                agg = working.groupby(group_cols, as_index=False).agg(
                    net_revenue=("line_revenue", "sum"),
                    list_revenue=("line_list_revenue", "sum"),
                    discount_weighted_num=("discount_weighted_num", "sum"),
                    high_discount_revenue=("high_discount_revenue", "sum"),
                    margin_at_risk=("margin_risk_revenue", "sum"),
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

            agg["weighted_discount_pct"] = _safe_ratio(
                agg["discount_weighted_num"], agg["list_revenue"]
            )
            agg["high_discount_revenue_share"] = _safe_ratio(
                agg["high_discount_revenue"], agg["net_revenue"]
            )
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


def _build_customer_pricing_rows(
    pricing: pd.DataFrame, selected_customers: set[str]
) -> pd.DataFrame:
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


def _select_dashboard_risk_rows(risk: pd.DataFrame) -> pd.DataFrame:
    """Keep every high-priority account, then fill the review queue to its target size."""
    ordered = risk.sort_values("governance_priority_score", ascending=False)
    priority_mask = ordered["risk_tier"].isin(["Critical", "High"])
    priority_rows = ordered.loc[priority_mask]
    remaining_slots = max(RISK_EXPORT_TARGET_ROWS - len(priority_rows), 0)
    review_rows = ordered.loc[~priority_mask].head(remaining_slots)
    return pd.concat([priority_rows, review_rows], ignore_index=True)


def build_executive_dashboard(
    processed_tables: dict[str, pd.DataFrame],
    dashboard_dir: Path,
) -> Path:
    dashboard_dir.mkdir(parents=True, exist_ok=True)

    pricing = processed_tables["order_item_pricing_metrics"].copy()
    risk = processed_tables["customer_risk_scores"].copy()
    dashboard_policy = load_dashboard_policy()
    margin_at_risk_proxy_max = get_margin_at_risk_proxy_max()

    pricing["order_date"] = pd.to_datetime(pricing["order_date"])
    pricing["order_month"] = pd.to_datetime(pricing["order_month"]).dt.strftime("%Y-%m")
    pricing["discount_weighted_num"] = pricing["discount_depth"] * pricing["line_list_revenue"]
    pricing["high_discount_revenue"] = np.where(
        pricing["high_discount_flag"] == 1, pricing["line_revenue"], 0.0
    )
    pricing["margin_risk_revenue"] = np.where(
        (pricing["high_discount_flag"] == 1)
        & (pricing["margin_proxy_pct"] < margin_at_risk_proxy_max),
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
    risk_export = _select_dashboard_risk_rows(risk_export)
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
        "policy": dashboard_policy,
    }
    data_json = _json_for_script(payload)

    html = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Pricing &amp; Discount Governance Dashboard</title>
  <meta name="description" content="Synthetic pricing governance analytics dashboard for detecting discount leakage, margin exposure, and commercial risk." />
  <meta name="theme-color" content="#0b0c0e" />
  <script>
    // Stamp the theme before first paint so the dark default (or a stored choice)
    // renders with no light flash. The main script re-applies it idempotently.
    (function () {
      try {
        var stored = localStorage.getItem('pricing_dashboard_theme');
        document.documentElement.setAttribute(
          'data-theme', stored === 'light' ? 'light' : 'dark'
        );
      } catch (_) {
        document.documentElement.setAttribute('data-theme', 'dark');
      }
    })();
  </script>
  <link rel="icon" href="data:," />
  <link rel="canonical" href="https://mfidalgomartins.github.io/pricing-discount-governance-system/pricing-discipline-command-center.html" />
  <meta property="og:title" content="Pricing &amp; Discount Governance Dashboard" />
  <meta property="og:description" content="Synthetic pricing governance analytics dashboard for discount leakage, margin exposure, and customer-level intervention planning." />
  <meta property="og:type" content="website" />
  <meta property="og:url" content="https://mfidalgomartins.github.io/pricing-discount-governance-system/pricing-discipline-command-center.html" />
  <meta name="twitter:card" content="summary_large_image" />
  <script src="vendor/chart.umd.min.js"></script>
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Geist:wght@400;500;600&family=Geist+Mono:wght@400;500&display=swap" rel="stylesheet" />
  <style>
    /*
      Colour law for this dashboard — three roles, never mixed:
        accent    the measured quantity in any comparison chart (one series, one colour)
        severity  policy state only: ok / warn / critical
        graphite  structure: bridge totals, grid, axes
      Mark and text steps are validated against the surfaces they render on
      (light #ffffff, dark #15171a): marks clear 3:1, text steps clear 4.5:1.
    */
    :root {
      color-scheme: light;
      --font-sans: "Geist", -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
      --font-mono: "Geist Mono", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;

      --plane:     #f4f4f2;
      --surface:   #ffffff;
      --surface-2: #fafaf9;
      --inset:     #eeeeec;

      --ink:       #101113;
      --ink-2:     #3c3f44;
      --muted:     #6b7076;
      --muted-2:   #71777f;

      --rule:      rgba(16, 17, 19, 0.09);
      --rule-2:    rgba(16, 17, 19, 0.16);
      --rule-3:    rgba(16, 17, 19, 0.28);

      --accent:    #2a5db0;
      --ok:        #1a7f37;
      --warn:      #b06000;
      --critical:  #c0362c;
      --graphite:  #7d848c;

      --accent-text:   #24519b;
      --ok-text:       #14682d;
      --warn-text:     #8a4b00;
      --critical-text: #a52a21;

      --accent-wash:   rgba(42, 93, 176, 0.10);
      --ok-wash:       rgba(26, 127, 55, 0.10);
      --warn-wash:     rgba(176, 96, 0, 0.13);
      --critical-wash: rgba(192, 54, 44, 0.13);

      --grid:      rgba(16, 17, 19, 0.07);
      --axis:      rgba(16, 17, 19, 0.18);

      --radius:    12px;
      --radius-sm: 7px;
      --focus:     0 0 0 2px var(--surface), 0 0 0 4px var(--accent);
      --card-shadow: 0 1px 2px rgba(16, 17, 19, 0.05);
      --page-max:  1320px;
    }

    [data-theme="dark"] {
      color-scheme: dark;
      --plane:     #0b0c0e;
      --surface:   #15171a;
      --surface-2: #1b1e22;
      --inset:     #101215;

      --ink:       #f2f4f6;
      --ink-2:     #c9ced5;
      --muted:     #939aa3;
      --muted-2:   #8b929b;

      --rule:      rgba(242, 244, 246, 0.10);
      --rule-2:    rgba(242, 244, 246, 0.18);
      --rule-3:    rgba(242, 244, 246, 0.30);

      --accent:    #3f74d6;
      --ok:        #279044;
      --warn:      #b8791c;
      --critical:  #d94f42;
      --graphite:  #767e8b;

      --accent-text:   #7ba3ea;
      --ok-text:       #4ec96a;
      --warn-text:     #e0a844;
      --critical-text: #ff8a7d;

      --accent-wash:   rgba(63, 116, 214, 0.14);
      --ok-wash:       rgba(39, 144, 68, 0.14);
      --warn-wash:     rgba(184, 121, 28, 0.16);
      --critical-wash: rgba(217, 79, 66, 0.16);

      --grid:      rgba(242, 244, 246, 0.08);
      --axis:      rgba(242, 244, 246, 0.20);
      --card-shadow: none;
    }

    *, *::before, *::after { box-sizing: border-box; }
    html { -webkit-font-smoothing: antialiased; -moz-osx-font-smoothing: grayscale; }

    body {
      margin: 0;
      font-family: var(--font-sans);
      background: var(--plane);
      color: var(--ink);
      font-size: 14.5px;
      line-height: 1.55;
      letter-spacing: -0.006em;
    }

    h1, h2, h3 { margin: 0; letter-spacing: -0.022em; font-weight: 600; }
    p { margin: 0; }

    .skip-link {
      position: absolute; left: -9999px; top: -9999px;
      background: var(--ink); color: var(--plane);
      padding: 9px 15px; font-size: 12px; font-weight: 500;
      border-radius: var(--radius-sm); z-index: 99;
    }
    .skip-link:focus { left: 16px; top: 16px; }

    .page {
      max-width: var(--page-max);
      margin: 0 auto;
      padding: 40px 32px 72px;
      display: flex; flex-direction: column;
      gap: 40px;
    }

    .eyebrow {
      font-size: 11px; font-weight: 500;
      letter-spacing: 0.10em; text-transform: uppercase;
      color: var(--muted-2);
    }

    /* ---------------- MASTHEAD ---------------- */

    .masthead {
      display: flex; align-items: flex-start; justify-content: space-between;
      gap: 24px; flex-wrap: wrap;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--rule-2);
    }
    .masthead-lead { display: flex; flex-direction: column; gap: 7px; }
    .masthead h1 { font-size: clamp(24px, 2.6vw, 31px); line-height: 1.12; }
    .masthead-side { display: flex; align-items: center; gap: 12px; }

    .posture {
      display: inline-flex; align-items: center; gap: 8px;
      padding: 6px 12px 6px 10px;
      border: 1px solid var(--rule-2);
      border-radius: 999px;
      background: var(--surface);
      font-size: 12.5px; font-weight: 500;
      color: var(--ink-2);
      white-space: nowrap;
    }
    .posture-dot {
      width: 7px; height: 7px; border-radius: 50%;
      background: var(--muted); flex: none;
    }
    .posture-ok       .posture-dot { background: var(--ok); }
    .posture-warn     .posture-dot { background: var(--warn); }
    .posture-critical .posture-dot { background: var(--critical); }
    .posture-ok       { border-color: var(--ok-wash);       background: var(--ok-wash); }
    .posture-warn     { border-color: var(--warn-wash);     background: var(--warn-wash); }
    .posture-critical { border-color: var(--critical-wash); background: var(--critical-wash); }

    .masthead-actions { display: inline-flex; gap: 6px; }

    .ghost-btn {
      font-family: var(--font-sans);
      font-size: 12.5px; font-weight: 500;
      background: var(--surface);
      border: 1px solid var(--rule-2);
      color: var(--ink-2);
      padding: 6px 12px;
      border-radius: var(--radius-sm);
      cursor: pointer;
      transition: border-color 0.14s, color 0.14s, background 0.14s;
    }
    .ghost-btn:hover { border-color: var(--rule-3); color: var(--ink); }
    .ghost-btn:focus-visible { outline: none; box-shadow: var(--focus); }

    /* ---------------- VERDICT ---------------- */

    .verdict {
      display: grid;
      grid-template-columns: minmax(0, 1.05fr) minmax(0, 1fr);
      gap: 0;
      background: var(--surface);
      border: 1px solid var(--rule);
      border-radius: var(--radius);
      box-shadow: var(--card-shadow);
      overflow: hidden;
    }
    .verdict-hero {
      display: flex; flex-direction: column; gap: 10px;
      padding: 28px 32px 30px;
      border-right: 1px solid var(--rule);
      position: relative;
    }
    .verdict-hero::before {
      content: ""; position: absolute; left: 0; top: 0; bottom: 0; width: 3px;
      background: var(--muted);
    }
    .verdict-ok       .verdict-hero::before { background: var(--ok); }
    .verdict-warn     .verdict-hero::before { background: var(--warn); }
    .verdict-critical .verdict-hero::before { background: var(--critical); }

    .verdict-label {
      font-size: 11px; font-weight: 500;
      letter-spacing: 0.10em; text-transform: uppercase;
      color: var(--muted-2);
    }
    .verdict-figure {
      font-size: clamp(46px, 5.6vw, 68px);
      font-weight: 600;
      line-height: 0.98;
      letter-spacing: -0.035em;
      color: var(--ink);
    }
    .verdict-read {
      font-size: 15px; line-height: 1.6;
      color: var(--ink-2);
      max-width: 46ch;
      margin-top: 2px;
    }

    .verdict-facts {
      margin: 0; padding: 0;
      display: flex; flex-direction: column;
      background: var(--surface-2);
    }
    .fact {
      padding: 18px 28px;
      border-bottom: 1px solid var(--rule);
      display: grid;
      grid-template-columns: 13ch minmax(0, 1fr);
      align-items: baseline;
      gap: 16px;
    }
    .fact:last-child { border-bottom: none; }
    .fact dt {
      font-size: 11px; font-weight: 500;
      letter-spacing: 0.08em; text-transform: uppercase;
      color: var(--muted-2);
    }
    .fact dd { margin: 0; display: flex; flex-direction: column; gap: 1px; min-width: 0; }
    .fact dd strong {
      font-size: 20px; font-weight: 600; line-height: 1.25;
      letter-spacing: -0.02em; color: var(--ink);
    }
    .fact dd span { font-size: 12.5px; color: var(--muted); line-height: 1.45; }

    /* ---------------- SECTION HEADS ---------------- */

    .section-head {
      display: flex; align-items: baseline; justify-content: space-between;
      gap: 28px; flex-wrap: wrap;
      padding-bottom: 10px;
      border-bottom: 1px solid var(--rule-2);
      margin-bottom: -16px;
    }
    .section-head-copy { display: flex; flex-direction: column; gap: 4px; }
    .kicker {
      font-size: 10.5px; font-weight: 500;
      letter-spacing: 0.12em; text-transform: uppercase;
      color: var(--muted-2);
    }
    .section-head h2 { font-size: 19px; line-height: 1.25; }
    .section-head > p { font-size: 13px; color: var(--muted); max-width: 60ch; }

    /* ---------------- SCOPE / FILTERS ---------------- */

    .filters-panel {
      background: var(--surface);
      border: 1px solid var(--rule);
      border-radius: var(--radius);
      box-shadow: var(--card-shadow);
      padding: 20px 24px 22px;
      display: flex; flex-direction: column; gap: 16px;
    }
    .scope-head {
      display: flex; align-items: center; justify-content: space-between;
      gap: 20px; flex-wrap: wrap;
    }
    .scope-head-copy { display: flex; align-items: baseline; gap: 14px; flex-wrap: wrap; }
    .scope-head h2 { font-size: 14px; }
    .scope-meta {
      font-family: var(--font-mono);
      font-size: 11.5px; color: var(--muted);
      letter-spacing: -0.01em;
    }

    .filters {
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 14px;
    }
    .field { display: flex; flex-direction: column; gap: 5px; min-width: 0; }
    .field label {
      font-size: 10.5px; font-weight: 500;
      letter-spacing: 0.08em; text-transform: uppercase;
      color: var(--muted-2);
    }
    .field select {
      font-family: var(--font-sans);
      font-size: 13.5px; font-weight: 500;
      color: var(--ink);
      background-color: var(--surface-2);
      border: 1px solid var(--rule-2);
      border-radius: var(--radius-sm);
      padding: 8px 28px 8px 10px;
      appearance: none; -webkit-appearance: none;
      background-image:
        linear-gradient(45deg, transparent 50%, currentColor 50%),
        linear-gradient(135deg, currentColor 50%, transparent 50%);
      background-position: right 13px center, right 8px center;
      background-size: 5px 5px, 5px 5px;
      background-repeat: no-repeat;
      cursor: pointer;
      width: 100%;
      transition: border-color 0.14s, background-color 0.14s;
    }
    .field select:hover { border-color: var(--rule-3); }
    .field select:focus-visible { outline: none; box-shadow: var(--focus); border-color: var(--accent); }

    /* ---------------- KPI TILES ---------------- */

    .kpis {
      display: grid;
      grid-template-columns: repeat(4, minmax(0, 1fr));
      gap: 16px;
    }
    .kpi {
      background: var(--surface);
      border: 1px solid var(--rule);
      border-radius: var(--radius);
      box-shadow: var(--card-shadow);
      padding: 18px 20px 20px;
      display: flex; flex-direction: column; gap: 12px;
      min-width: 0;
    }
    .kpi-head { display: flex; align-items: center; justify-content: space-between; gap: 10px; }
    .kpi-title {
      font-size: 12.5px; font-weight: 500;
      color: var(--muted);
    }
    .kpi-state {
      display: inline-flex; align-items: center; gap: 5px;
      font-size: 11px; font-weight: 500;
      color: var(--muted);
      white-space: nowrap;
    }
    .kpi-state i {
      width: 6px; height: 6px; border-radius: 50%;
      background: currentColor; flex: none;
    }
    .kpi-state-ok       { color: var(--ok-text); }
    .kpi-state-warn     { color: var(--warn-text); }
    .kpi-state-critical { color: var(--critical-text); }
    .kpi-state-neutral  { color: var(--muted); }

    .kpi-value {
      font-size: clamp(28px, 2.9vw, 36px);
      font-weight: 600;
      line-height: 1.0;
      letter-spacing: -0.03em;
      color: var(--ink);
    }
    .kpi-detail {
      font-size: 12.5px; line-height: 1.5;
      color: var(--muted);
    }

    /* Policy gauge: zones carry the thresholds, the needle carries the value. */
    .meter { position: relative; height: 10px; margin: 2px 0 4px; }
    .meter-zones {
      position: absolute; inset: 0;
      border-radius: 3px;
      background: linear-gradient(to right,
        var(--ok-wash) 0, var(--ok-wash) var(--warn-at),
        var(--warn-wash) var(--warn-at), var(--warn-wash) var(--crit-at),
        var(--critical-wash) var(--crit-at), var(--critical-wash) 100%);
    }
    .meter-track {
      position: absolute; inset: 0;
      border-radius: 3px; background: var(--inset);
    }
    .meter-fill {
      position: absolute; left: 0; top: 0; bottom: 0;
      border-radius: 3px; background: var(--accent);
    }
    .meter-needle {
      position: absolute; top: -3px; height: 16px; width: 2px;
      border-radius: 1px; background: var(--muted);
      transform: translateX(-1px);
    }
    .meter-needle-ok       { background: var(--ok); }
    .meter-needle-warn     { background: var(--warn); }
    .meter-needle-critical { background: var(--critical); }

    /* ---------------- PANELS & CHARTS ---------------- */

    .panel {
      background: var(--surface);
      border: 1px solid var(--rule);
      border-radius: var(--radius);
      box-shadow: var(--card-shadow);
      padding: 20px 22px 18px;
      display: flex; flex-direction: column; gap: 14px;
      min-width: 0;
    }
    .panel-head { display: flex; flex-direction: column; gap: 4px; }
    .panel-head h3 { font-size: 16px; line-height: 1.3; }
    .panel-head > p { font-size: 12.5px; color: var(--muted); line-height: 1.5; }

    .answer {
      font-size: 13.5px; line-height: 1.5;
      color: var(--ink-2);
      font-weight: 500;
      padding: 10px 12px;
      background: var(--surface-2);
      border-left: 2px solid var(--rule-3);
      border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
    }

    .charts {
      display: grid;
      grid-template-columns: repeat(12, minmax(0, 1fr));
      gap: 16px;
    }
    .span-7 { grid-column: span 7; }
    .span-5 { grid-column: span 5; }
    .span-6 { grid-column: span 6; }

    .chart-wrap { position: relative; width: 100%; height: 264px; }
    .chart-wrap-tall { height: 340px; }

    .chart-data summary {
      font-size: 11.5px; font-weight: 500;
      color: var(--muted);
      cursor: pointer;
      padding: 8px 0 0;
      list-style: none;
      border-top: 1px solid var(--rule);
      display: flex; align-items: center; justify-content: space-between;
    }
    .chart-data summary::-webkit-details-marker { display: none; }
    .chart-data summary::after {
      content: "+"; font-family: var(--font-mono); color: var(--muted-2);
    }
    .chart-data[open] summary::after { content: "\2212"; }
    .chart-data summary:hover { color: var(--ink-2); }
    .chart-data summary:focus-visible { outline: none; box-shadow: var(--focus); border-radius: 3px; }
    .chart-data table {
      width: 100%; border-collapse: collapse;
      font-family: var(--font-mono);
      font-size: 11.5px;
      margin-top: 8px;
    }
    .chart-data th, .chart-data td {
      padding: 5px 10px 5px 0; text-align: left;
      border-bottom: 1px solid var(--rule);
      color: var(--ink-2);
      font-variant-numeric: tabular-nums;
    }
    .chart-data th { color: var(--muted-2); font-weight: 500; }

    /* ---------------- QUEUE TABLE ---------------- */

    .table-panel { gap: 16px; padding-bottom: 20px; }
    .table-head {
      display: flex; align-items: baseline; justify-content: space-between;
      gap: 24px; flex-wrap: wrap;
    }
    .table-head-copy { display: flex; flex-direction: column; gap: 4px; }
    .table-head h3 { font-size: 16px; }
    .table-head-copy > p { font-size: 12.5px; color: var(--muted); max-width: 62ch; }
    .table-toolbar { display: flex; align-items: baseline; gap: 16px; }
    .table-count {
      font-family: var(--font-mono);
      font-size: 12px; color: var(--ink-2);
      font-variant-numeric: tabular-nums;
    }
    .sort-note { font-size: 11.5px; color: var(--muted-2); }

    .table-wrap {
      overflow: auto;
      max-height: 620px;
      border: 1px solid var(--rule);
      border-radius: var(--radius-sm);
    }
    #riskTable { width: 100%; border-collapse: collapse; font-size: 13px; }
    #riskTable thead th {
      position: sticky; top: 0; z-index: 1;
      background: var(--surface-2);
      text-align: left;
      padding: 10px 14px;
      font-size: 10.5px; font-weight: 500;
      letter-spacing: 0.08em; text-transform: uppercase;
      color: var(--muted-2);
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
    .sort-button:focus-visible { outline: none; box-shadow: var(--focus); border-radius: 3px; }
    [aria-sort="ascending"] .sort-button::after  { content: "\2191"; color: var(--accent-text); }
    [aria-sort="descending"] .sort-button::after { content: "\2193"; color: var(--accent-text); }

    #riskTable td {
      padding: 10px 14px;
      border-bottom: 1px solid var(--rule);
      color: var(--ink-2);
      vertical-align: middle;
      white-space: nowrap;
    }
    #riskTable tbody tr:last-child td { border-bottom: none; }
    #riskTable tbody tr:hover td { background: var(--surface-2); }
    #riskTable td.num, #riskTable td.rank-col {
      font-family: var(--font-mono);
      font-variant-numeric: tabular-nums;
      font-size: 12px;
    }
    #riskTable td.rank-col { color: var(--muted-2); padding-right: 4px; }
    #riskTable td.id-col { font-family: var(--font-mono); font-size: 12px; color: var(--ink); }
    #riskTable td.empty-cell {
      padding: 28px 14px; text-align: center;
      color: var(--muted); white-space: normal;
    }

    .tier-chip {
      display: inline-flex; align-items: center; gap: 6px;
      font-size: 12px; font-weight: 500;
      color: var(--ink-2);
      white-space: nowrap;
    }
    .tier-chip i { width: 6px; height: 6px; border-radius: 50%; background: var(--muted); flex: none; }
    .tier-critical i { background: var(--critical); }
    .tier-high     i { background: var(--warn); }
    .tier-medium   i { background: var(--accent); }
    .tier-low      i { background: var(--ok); }

    /* ---------------- COLOPHON ---------------- */

    .colophon {
      display: flex; flex-wrap: wrap; gap: 6px 18px;
      padding-top: 18px;
      border-top: 1px solid var(--rule-2);
      font-size: 11.5px; color: var(--muted-2);
    }
    .colophon span:not(:last-child)::after {
      content: "·"; margin-left: 18px; color: var(--rule-3);
    }

    /* ---------------- RESPONSIVE ---------------- */

    @media (max-width: 1080px) {
      .verdict { grid-template-columns: 1fr; }
      .verdict-hero { border-right: none; border-bottom: 1px solid var(--rule); }
      .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .filters { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .span-7, .span-5, .span-6 { grid-column: span 12; }
    }

    @media (max-width: 640px) {
      .page { padding: 28px 16px 56px; gap: 28px; }
      .kpis { grid-template-columns: 1fr; }
      .filters { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .verdict-hero { padding: 22px 20px 24px; }
      .fact { grid-template-columns: 1fr; gap: 4px; padding: 14px 20px; }
      .masthead-side { width: 100%; justify-content: space-between; }
      .chart-wrap { height: 240px; }
      .chart-wrap-tall { height: 300px; }
    }

    @media (prefers-reduced-motion: reduce) {
      * { transition: none !important; animation: none !important; }
    }

    /* ---------------- PRINT ---------------- */

    @media print {
      :root {
        --plane: #ffffff; --surface: #ffffff; --surface-2: #ffffff;
        --ink: #101113; --muted: #4a4a4a; --card-shadow: none;
      }
      body { background: #ffffff !important; -webkit-print-color-adjust: exact; print-color-adjust: exact; }
      .page { max-width: none; padding: 10mm 12mm; gap: 22px; }
      .masthead-actions, .filters, #resetFiltersBtn { display: none !important; }
      .panel, .kpi, .verdict, .table-panel { break-inside: avoid; page-break-inside: avoid; }
      .chart-wrap { height: 210px; }
      .chart-wrap-tall { height: 260px; }
      .table-wrap { max-height: none; overflow: visible; }
      .chart-data { display: none; }
    }
  </style>
</head>
<body>
<a class="skip-link" href="#mainContent">Skip to dashboard content</a>
<main class="page" id="mainContent">

  <header class="masthead">
    <div class="masthead-lead">
      <p class="eyebrow">Commercial governance &middot; Synthetic portfolio</p>
      <h1>Pricing Discipline Command Center</h1>
    </div>
    <div class="masthead-side">
      <div class="posture" id="posturePill">
        <span class="posture-dot"></span>
        <span class="posture-label" id="postureLabel">Assessing</span>
      </div>
      <div class="masthead-actions">
        <button id="themeToggle" class="ghost-btn" type="button" aria-label="Toggle colour mode">Dark</button>
        <button id="printBtn" class="ghost-btn" type="button" aria-label="Print dashboard">Print</button>
      </div>
    </div>
  </header>

  <section class="verdict" id="verdictBlock" aria-labelledby="verdictLabel">
    <div class="verdict-hero">
      <p class="verdict-label" id="verdictLabel">Value surrendered from list price</p>
      <p class="verdict-figure" id="heroLeakage">&mdash;</p>
      <p class="verdict-read" id="heroCallout">Reading the current pricing posture for the selected scope.</p>
    </div>
    <dl class="verdict-facts">
      <div class="fact">
        <dt>Revenue exposed</dt>
        <dd><strong id="decisionMatter">&mdash;</strong><span id="decisionMatterNote">Value in the margin-risk zone</span></dd>
      </div>
      <div class="fact">
        <dt>Risk driver</dt>
        <dd><strong id="decisionCritical">&mdash;</strong><span id="decisionCriticalNote">Largest source of concentration</span></dd>
      </div>
      <div class="fact">
        <dt>Next move</dt>
        <dd><strong id="decisionAction">&mdash;</strong><span id="decisionActionNote">Leading action in the queue</span></dd>
      </div>
    </dl>
  </section>

  <section class="filters-panel" aria-labelledby="scopeTitle">
    <div class="scope-head">
      <div class="scope-head-copy">
        <h2 id="scopeTitle">Scope</h2>
        <p class="scope-meta" id="controlsMeta"></p>
      </div>
      <button id="resetFiltersBtn" class="ghost-btn" type="button">Reset</button>
    </div>
    <div class="filters">
      <div class="field"><label for="periodStartFilter">Start month</label><select id="periodStartFilter"></select></div>
      <div class="field"><label for="periodEndFilter">End month</label><select id="periodEndFilter"></select></div>
      <div class="field"><label for="segmentFilter">Segment</label><select id="segmentFilter"></select></div>
      <div class="field"><label for="regionFilter">Region</label><select id="regionFilter"></select></div>
      <div class="field"><label for="categoryFilter">Category</label><select id="categoryFilter"></select></div>
      <div class="field"><label for="channelFilter">Channel</label><select id="channelFilter"></select></div>
    </div>
  </section>

  <div class="section-head">
    <div class="section-head-copy">
      <span class="kicker">Posture</span>
      <h2>Governed metrics</h2>
    </div>
    <p>Each gauge reads the metric against the warning and critical lines set in governance policy.</p>
  </div>
  <section class="kpis">
    <article class="kpi" id="kpiRevenueCard">
      <div class="kpi-head">
        <h3 class="kpi-title">Revenue in scope</h3>
        <span class="kpi-state kpi-state-neutral" id="kpiRevenueState"><i></i>Coverage</span>
      </div>
      <p class="kpi-value" id="kpiRevenue">&mdash;</p>
      <div class="meter" id="kpiRevenueMeter" aria-hidden="true"></div>
      <p class="kpi-detail" id="kpiRevenueDetail">Share of period revenue under the current scope.</p>
    </article>
    <article class="kpi" id="kpiDiscountCard">
      <div class="kpi-head">
        <h3 class="kpi-title">Weighted discount</h3>
        <span class="kpi-state kpi-state-neutral" id="kpiDiscountState"><i></i>Reading</span>
      </div>
      <p class="kpi-value" id="kpiDiscount">&mdash;</p>
      <div class="meter" id="kpiDiscountMeter" aria-hidden="true"></div>
      <p class="kpi-detail" id="kpiDiscountDetail">List-price leakage weighted by revenue.</p>
    </article>
    <article class="kpi" id="kpiMarginRiskCard">
      <div class="kpi-head">
        <h3 class="kpi-title">Margin at risk</h3>
        <span class="kpi-state kpi-state-neutral" id="kpiMarginRiskState"><i></i>Reading</span>
      </div>
      <p class="kpi-value" id="kpiMarginRisk">&mdash;</p>
      <div class="meter" id="kpiMarginRiskMeter" aria-hidden="true"></div>
      <p class="kpi-detail" id="kpiMarginRiskDetail">High-discount and weak-margin overlap.</p>
    </article>
    <article class="kpi" id="kpiHighRiskCard">
      <div class="kpi-head">
        <h3 class="kpi-title">High-risk accounts</h3>
        <span class="kpi-state kpi-state-neutral" id="kpiHighRiskState"><i></i>Reading</span>
      </div>
      <p class="kpi-value" id="kpiHighRisk">&mdash;</p>
      <div class="meter" id="kpiHighRiskMeter" aria-hidden="true"></div>
      <p class="kpi-detail" id="kpiHighRiskDetail">Accounts in the critical and high tiers.</p>
    </article>
  </section>

  <div class="section-head">
    <div class="section-head-copy">
      <span class="kicker">Value bridge</span>
      <h2>Where list value goes</h2>
    </div>
    <p>List revenue, less the discount given away, less the share of what remains that sits in the margin-risk zone.</p>
  </div>
  <section class="panel" aria-labelledby="bridgeChartTitle">
    <div class="panel-head">
      <h3 id="bridgeChartTitle">Leakage bridge</h3>
      <p>Grey bars are totals; coloured bars are the value removed at each step.</p>
    </div>
    <p class="answer" id="bridgeChartAnswer">Reading the value bridge.</p>
    <div class="chart-wrap chart-wrap-tall"><canvas id="bridgeChart" aria-label="Bridge from list revenue to protected revenue" aria-describedby="bridgeChartAnswer bridgeChartData"></canvas></div>
    <details class="chart-data"><summary>Chart data</summary><div id="bridgeChartData"></div></details>
  </section>

  <div class="section-head">
    <div class="section-head-copy">
      <span class="kicker">Diagnostics</span>
      <h2>Where discipline breaks</h2>
    </div>
    <p>Momentum against policy first, then the segments, regions and actions carrying the exposure.</p>
  </div>
  <section class="charts">
    <article class="panel span-7" aria-labelledby="trendChartTitle">
      <div class="panel-head">
        <span class="kicker">Momentum</span>
        <h3 id="trendChartTitle">Weighted discount against policy</h3>
        <p>Monthly list-price leakage, with the warning and critical lines.</p>
      </div>
      <p class="answer" id="trendChartAnswer">Reading the trend.</p>
      <div class="chart-wrap"><canvas id="trendChart" aria-label="Monthly weighted discount trend against policy thresholds" aria-describedby="trendChartAnswer trendChartData"></canvas></div>
      <details class="chart-data"><summary>Chart data</summary><div id="trendChartData"></div></details>
    </article>

    <article class="panel span-5" aria-labelledby="segmentChartTitle">
      <div class="panel-head">
        <span class="kicker">Concentration</span>
        <h3 id="segmentChartTitle">Discount depth by segment</h3>
        <p>Revenue-weighted discount, ranked.</p>
      </div>
      <p class="answer" id="segmentChartAnswer">Reading segment concentration.</p>
      <div class="chart-wrap"><canvas id="segmentChart" aria-label="Weighted discount by segment" aria-describedby="segmentChartAnswer segmentChartData"></canvas></div>
      <details class="chart-data"><summary>Chart data</summary><div id="segmentChartData"></div></details>
    </article>

    <article class="panel span-6" aria-labelledby="regionRiskChartTitle">
      <div class="panel-head">
        <span class="kicker">Exposure</span>
        <h3 id="regionRiskChartTitle">Margin at risk by region</h3>
        <p>Revenue caught in the high-discount, weak-margin overlap.</p>
      </div>
      <p class="answer" id="regionRiskChartAnswer">Reading regional exposure.</p>
      <div class="chart-wrap"><canvas id="regionRiskChart" aria-label="Margin at risk by region" aria-describedby="regionRiskChartAnswer regionRiskChartData"></canvas></div>
      <details class="chart-data"><summary>Chart data</summary><div id="regionRiskChartData"></div></details>
    </article>

    <article class="panel span-6" aria-labelledby="actionChartTitle">
      <div class="panel-head">
        <span class="kicker">Workload</span>
        <h3 id="actionChartTitle">Revenue by recommended action</h3>
        <p>What the review queue is asking the commercial team to do.</p>
      </div>
      <p class="answer" id="actionChartAnswer">Reading the workload mix.</p>
      <div class="chart-wrap"><canvas id="actionChart" aria-label="Revenue by recommended intervention action" aria-describedby="actionChartAnswer actionChartData"></canvas></div>
      <details class="chart-data"><summary>Chart data</summary><div id="actionChartData"></div></details>
    </article>
  </section>

  <section class="panel table-panel" aria-labelledby="queueTitle">
    <div class="table-head">
      <div class="table-head-copy">
        <span class="kicker">Operating detail</span>
        <h3 id="queueTitle">Customer review queue</h3>
        <p>Accounts ranked by governance priority, with the discount evidence behind each score and the recommended action.</p>
      </div>
      <div class="table-toolbar">
        <span class="table-count" id="tableCount">&mdash;</span>
        <p class="sort-note" id="tableSortMeta" aria-live="polite">Sorted by priority score.</p>
      </div>
    </div>
    <div class="table-wrap">
      <table id="riskTable">
        <thead>
          <tr>
            <th class="rank-col" scope="col">#</th>
            <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-key="customer_id">Customer</button></th>
            <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-key="segment">Segment</button></th>
            <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-key="region">Region</button></th>
            <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-key="filtered_revenue">Revenue</button></th>
            <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-key="filtered_avg_discount">Avg discount</button></th>
            <th scope="col" aria-sort="descending"><button type="button" class="sort-button" data-key="governance_priority_score">Score</button></th>
            <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-key="risk_tier">Risk tier</button></th>
            <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-key="main_risk_driver">Risk driver</button></th>
            <th scope="col" aria-sort="none"><button type="button" class="sort-button" data-key="recommended_action">Recommended action</button></th>
          </tr>
        </thead>
        <tbody></tbody>
      </table>
    </div>
  </section>

  <footer class="colophon">
    <span id="coverageMeta"></span>
    <span>Synthetic data</span>
    <span>Decision-support heuristic, not causal attribution</span>
  </footer>

</main>

<script>
const DATA = __DATA_JSON__;
const ALL = "__ALL_VALUE__";
const THEME_STORAGE_KEY = 'pricing_dashboard_theme';
const POLICY = DATA.policy || {};
const KPI_POLICY = POLICY.thresholds || {};
const POSTURE_POLICY = POLICY.thresholds || {};

/* Each policy gauge puts its critical line at 75% of the track, so the scale is
   fixed by policy rather than by the data currently in view. */
const GAUGE_CRITICAL_AT = 0.75;

Chart.defaults.font.family = '"Geist", -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif';
Chart.defaults.font.size = 11.5;
Chart.defaults.plugins.legend.display = false;
Chart.defaults.plugins.tooltip.backgroundColor = '#101113';
Chart.defaults.plugins.tooltip.titleFont = { family: '"Geist", sans-serif', size: 11.5, weight: '500' };
Chart.defaults.plugins.tooltip.bodyFont = { family: '"Geist Mono", monospace', size: 11.5 };
Chart.defaults.plugins.tooltip.padding = 10;
Chart.defaults.plugins.tooltip.cornerRadius = 6;
Chart.defaults.plugins.tooltip.displayColors = false;
Chart.defaults.maintainAspectRatio = false;

const MONO_FONT = '500 11px "Geist Mono", monospace';

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
const dims = ['segment', 'region', 'category', 'sales_channel'];

/* ---------------- formatting ---------------- */

const fmtCurrency = (n) => (Number(n) || 0).toLocaleString('en-US', {
  style: 'currency', currency: 'USD', maximumFractionDigits: 0
});

const fmtPct = (n, digits = 1) => `${((Number(n) || 0) * 100).toFixed(digits)}%`;

const fmtCompactUsd = (value) => {
  const v = Number(value) || 0;
  const abs = Math.abs(v);
  if (abs >= 1e9) return `$${(v / 1e9).toFixed(2)}B`;
  if (abs >= 1e6) return `$${(v / 1e6).toFixed(1)}M`;
  if (abs >= 1e3) return `$${(v / 1e3).toFixed(0)}K`;
  return `$${v.toFixed(0)}`;
};

const fmtAxisUsd = (value) => fmtCompactUsd(value);

const fmtCount = (n) => (Number(n) || 0).toLocaleString('en-US');

function fmtMonth(yyyymm) {
  if (!yyyymm || !/^\d{4}-\d{2}$/.test(yyyymm)) return yyyymm || '';
  const [year, month] = yyyymm.split('-');
  return new Date(Number(year), Number(month) - 1, 1)
    .toLocaleDateString('en-US', { month: 'short', year: 'numeric' });
}

function compactLabel(label, maxLen = 26) {
  const value = String(label || '');
  return value.length <= maxLen ? value : `${value.slice(0, maxLen - 1)}…`;
}

function titleCaseLabel(value) {
  return String(value || '').replaceAll('_', ' ').replace(/\b\w/g, (m) => m.toUpperCase());
}

function scoreComponentLabel(value) {
  const labels = {
    pricing_risk_score: 'Price variance',
    discount_dependency_score: 'Discount dependency',
    margin_erosion_score: 'Margin erosion'
  };
  return labels[value] || titleCaseLabel(value);
}

function thresholdGapLabel(value, warnThreshold) {
  const diffPts = ((Number(value) || 0) - Number(warnThreshold || 0)) * 100;
  if (Math.abs(diffPts) < 0.05) return 'sitting on the warning line';
  return diffPts > 0
    ? `${diffPts.toFixed(1)} pts above the ${fmtPct(warnThreshold)} warning line`
    : `${Math.abs(diffPts).toFixed(1)} pts below the ${fmtPct(warnThreshold)} warning line`;
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

function getCssVar(name) {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
}

function getThemePalette() {
  return {
    axisText: getCssVar('--muted'),
    grid: getCssVar('--grid'),
    axis: getCssVar('--axis'),
    accent: getCssVar('--accent'),
    accentWash: getCssVar('--accent-wash'),
    ok: getCssVar('--ok'),
    warn: getCssVar('--warn'),
    critical: getCssVar('--critical'),
    criticalWash: getCssVar('--critical-wash'),
    graphite: getCssVar('--graphite'),
    surface: getCssVar('--surface'),
    ink: getCssVar('--ink'),
    ink2: getCssVar('--ink-2')
  };
}

/* ---------------- chart plugins ---------------- */

/* Vertical crosshair on the active index of the trend line. */
const crosshair = {
  id: 'crosshair',
  afterDatasetsDraw(chart, _args, opts) {
    if (!opts || !opts.color || !chart.chartArea) return;
    const active = chart.tooltip ? chart.tooltip.getActiveElements() : [];
    if (!active.length) return;
    const { ctx, chartArea } = chart;
    ctx.save();
    ctx.strokeStyle = opts.color;
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(active[0].element.x, chartArea.top);
    ctx.lineTo(active[0].element.x, chartArea.bottom);
    ctx.stroke();
    ctx.restore();
  }
};

/* Policy threshold lines, plus a wash over the critical zone. */
const policyLines = {
  id: 'policyLines',
  beforeDatasetsDraw(chart, _args, opts) {
    if (!opts || !opts.lines || !chart.chartArea) return;
    const { ctx, chartArea, scales } = chart;
    ctx.save();
    /* The critical zone is everything above the line, so it fills from the top
       of the plot down to it — not from the line down to the baseline. */
    if (opts.zoneFrom != null && opts.zoneColor) {
      const y = scales.y.getPixelForValue(opts.zoneFrom);
      const floor = Math.max(chartArea.top, Math.min(y, chartArea.bottom));
      if (floor > chartArea.top) {
        ctx.fillStyle = opts.zoneColor;
        ctx.fillRect(chartArea.left, chartArea.top, chartArea.width, floor - chartArea.top);
      }
    }
    ctx.font = MONO_FONT;
    opts.lines.forEach((line) => {
      const py = scales.y.getPixelForValue(line.value);
      if (py < chartArea.top || py > chartArea.bottom) return;
      ctx.strokeStyle = line.color;
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.moveTo(chartArea.left, py);
      ctx.lineTo(chartArea.right, py);
      ctx.stroke();
      ctx.fillStyle = opts.labelColor;
      ctx.textAlign = 'right';
      ctx.textBaseline = 'bottom';
      ctx.fillText(line.label, chartArea.right - 2, py - 3);
    });
    ctx.restore();
  }
};

/* Bridge connectors and per-bar value captions. */
const bridgeDecor = {
  id: 'bridgeDecor',
  afterDatasetsDraw(chart, _args, opts) {
    if (!opts || !opts.rows || !chart.chartArea) return;
    const meta = chart.getDatasetMeta(0);
    if (!meta || !meta.data.length) return;
    const { ctx, scales } = chart;
    ctx.save();

    ctx.strokeStyle = opts.connector;
    ctx.lineWidth = 1;
    for (let i = 0; i < opts.rows.length - 1; i += 1) {
      const carry = opts.rows[i].carry;
      const a = meta.data[i];
      const b = meta.data[i + 1];
      if (carry == null || !a || !b) continue;
      const py = scales.y.getPixelForValue(carry);
      ctx.beginPath();
      ctx.moveTo(a.x + a.width / 2, py);
      ctx.lineTo(b.x - b.width / 2, py);
      ctx.stroke();
    }

    /* A caption is only drawn when it fits its category slot; otherwise it is
       dropped and the chart-data table carries the value instead. */
    ctx.font = MONO_FONT;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'bottom';
    const slot = chart.chartArea.width / Math.max(opts.rows.length, 1);
    opts.rows.forEach((row, i) => {
      const el = meta.data[i];
      if (!el || !row.tag) return;
      if (ctx.measureText(row.tag).width > slot - 6) return;
      const top = Math.min(
        scales.y.getPixelForValue(row.range[0]),
        scales.y.getPixelForValue(row.range[1])
      );
      ctx.fillStyle = row.total ? opts.labelMuted : opts.label;
      ctx.fillText(row.tag, el.x, top - 8);
    });
    ctx.restore();
  }
};

/* Direct value labels at bar caps (vertical) or tips (horizontal). */
const barTipLabels = {
  id: 'barTipLabels',
  afterDatasetsDraw(chart, _args, opts) {
    if (!opts || !opts.labels) return;
    const meta = chart.getDatasetMeta(0);
    if (!meta || !meta.data.length) return;
    const ctx = chart.ctx;
    const horizontal = chart.options.indexAxis === 'y';
    ctx.save();
    ctx.font = MONO_FONT;
    ctx.fillStyle = opts.color;
    const slot = chart.chartArea
      ? chart.chartArea.width / Math.max(opts.labels.length, 1)
      : Infinity;
    meta.data.forEach((el, i) => {
      const text = opts.labels[i];
      if (text == null) return;
      if (horizontal) {
        ctx.textAlign = 'left';
        ctx.textBaseline = 'middle';
        ctx.fillText(text, el.x + 8, el.y);
      } else {
        if (ctx.measureText(text).width > slot - 6) return;
        ctx.textAlign = 'center';
        ctx.textBaseline = 'bottom';
        ctx.fillText(text, el.x, el.y - 7);
      }
    });
    ctx.restore();
  }
};

Chart.register(crosshair, policyLines, bridgeDecor, barTipLabels);

/* ---------------- theme ---------------- */

function applyTheme(theme, persist = false) {
  const resolved = theme === 'dark' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', resolved);
  Chart.defaults.color = getCssVar('--muted');
  Chart.defaults.borderColor = getCssVar('--grid');
  Chart.defaults.plugins.tooltip.backgroundColor = resolved === 'dark' ? '#2a2e34' : '#101113';
  if (themeToggleEl) themeToggleEl.textContent = resolved === 'dark' ? 'Light' : 'Dark';
  if (persist) {
    try { localStorage.setItem(THEME_STORAGE_KEY, resolved); } catch (_) {}
  }
}

function initialTheme() {
  // A stored choice always wins, so the toggle keeps working across reloads.
  // Absent one, the command center opens dark by default.
  let stored = null;
  try { stored = localStorage.getItem(THEME_STORAGE_KEY); } catch (_) {}
  if (stored === 'light' || stored === 'dark') return stored;
  return 'dark';
}

/* ---------------- data shaping ---------------- */

function populateSelect(el, values) {
  const isMonth = el.id === 'periodStartFilter' || el.id === 'periodEndFilter';
  el.innerHTML = values
    .map((v) => `<option value="${escapeHtml(v)}">${escapeHtml(isMonth ? fmtMonth(v) : v)}</option>`)
    .join('');
}

function getFilters() {
  const periodStart = filterEls.period_start.value;
  const periodEnd = filterEls.period_end.value;
  const inOrder = periodStart <= periodEnd;
  return {
    segment: filterEls.segment.value,
    region: filterEls.region.value,
    category: filterEls.category.value,
    sales_channel: filterEls.sales_channel.value,
    period_start: inOrder ? periodStart : periodEnd,
    period_end: inOrder ? periodEnd : periodStart
  };
}

function matchesBaseRow(row, filters) {
  return dims.every((dim) => filters[dim] === ALL || row[dim] === filters[dim]);
}

function matchesPeriod(row, filters) {
  if (!row.order_month) return true;
  return row.order_month >= filters.period_start && row.order_month <= filters.period_end;
}

function aggregateScopedPricing(filters) {
  const agg = { line_revenue: 0, line_list_revenue: 0, discount_weighted_num: 0, margin_risk_revenue: 0 };
  DATA.pricingAggRows.forEach((row) => {
    if (!matchesBaseRow(row, filters) || !matchesPeriod(row, filters)) return;
    agg.line_revenue += Number(row.line_revenue) || 0;
    agg.line_list_revenue += Number(row.line_list_revenue) || 0;
    agg.discount_weighted_num += Number(row.discount_weighted_num) || 0;
    agg.margin_risk_revenue += Number(row.margin_risk_revenue) || 0;
  });
  return {
    net_revenue: agg.line_revenue,
    list_revenue: agg.line_list_revenue,
    leakage: agg.discount_weighted_num,
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
      map.set(id, { filtered_revenue: 0, filtered_list_revenue: 0, filtered_discount_num: 0 });
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

  if (Number(kpi.weighted_discount_pct || 0) >= discountCritical ||
      Number(kpi.margin_risk_share || 0) >= marginCritical ||
      Number(kpi.high_risk_count || 0) >= riskCritical) {
    return {
      level: 'critical',
      label: 'Intervene now',
      narrative: 'This scope breaches a critical governance line and belongs in immediate commercial review.'
    };
  }
  if (Number(kpi.weighted_discount_pct || 0) >= discountWarn ||
      Number(kpi.margin_risk_share || 0) >= marginWarn ||
      Number(kpi.high_risk_count || 0) >= riskWarn) {
    return {
      level: 'warn',
      label: 'Tight watch',
      narrative: 'This scope has crossed a warning line but has not reached a critical threshold.'
    };
  }
  return {
    level: 'ok',
    label: 'Controlled',
    narrative: 'This scope sits inside the monitoring range and shows no broad intervention pressure.'
  };
}

/* ---------------- meters ---------------- */

function renderPolicyMeter(id, value, warn, critical, level) {
  const el = document.getElementById(id);
  if (!el) return;
  const max = critical > 0 ? critical / GAUGE_CRITICAL_AT : 1;
  const at = (v) => `${Math.max(0, Math.min(100, (Number(v) || 0) / max * 100)).toFixed(2)}%`;
  el.innerHTML =
    `<span class="meter-zones" style="--warn-at:${at(warn)};--crit-at:${at(critical)}"></span>` +
    `<span class="meter-needle meter-needle-${level}" style="left:${at(value)}"></span>`;
}

function renderCoverageMeter(id, share) {
  const el = document.getElementById(id);
  if (!el) return;
  const pct = `${Math.max(0, Math.min(100, (Number(share) || 0) * 100)).toFixed(2)}%`;
  el.innerHTML = `<span class="meter-track"></span><span class="meter-fill" style="width:${pct}"></span>`;
}

function applyStateTag(id, level, label) {
  const el = document.getElementById(id);
  if (!el) return;
  el.className = `kpi-state kpi-state-${level}`;
  el.innerHTML = `<i></i>${escapeHtml(label)}`;
}

/* ---------------- KPIs ---------------- */

function updateKpis(filters, riskRows) {
  const kpi = aggregateScopedPricing(filters);
  const netRevenue = Number(kpi.net_revenue) || 0;
  const marginRiskShare = netRevenue > 0 ? (Number(kpi.margin_at_risk) || 0) / netRevenue : 0;
  const periodKpi = aggregateScopedPricing({
    ...filters, segment: ALL, region: ALL, category: ALL, sales_channel: ALL
  });
  const revenueShare = Number(periodKpi.net_revenue) > 0 ? netRevenue / Number(periodKpi.net_revenue) : 0;
  const highRiskCount = riskRows.filter((r) => r.risk_tier === 'High' || r.risk_tier === 'Critical').length;

  const discountWarn = Number(KPI_POLICY.weighted_discount_warn ?? 0.14);
  const discountCritical = Number(KPI_POLICY.weighted_discount_critical ?? 0.20);
  const marginWarn = Number(KPI_POLICY.margin_risk_share_warn ?? 0.12);
  const marginCritical = Number(KPI_POLICY.margin_risk_share_critical ?? 0.20);
  const riskWarn = Number(KPI_POLICY.high_risk_count_warn ?? 35);
  const riskCritical = Number(KPI_POLICY.high_risk_count_critical ?? 80);

  const level = (value, warn, critical) => value >= critical ? 'critical' : value >= warn ? 'warn' : 'ok';
  const stateLabel = (lvl) => lvl === 'critical' ? 'Critical' : lvl === 'warn' ? 'Watch' : 'Stable';

  setText('kpiRevenue', fmtCompactUsd(netRevenue));
  renderCoverageMeter('kpiRevenueMeter', revenueShare);
  applyStateTag('kpiRevenueState', 'neutral', 'Coverage');
  setText('kpiRevenueDetail', `${fmtPct(revenueShare)} of the revenue booked in this period is inside the current scope.`);

  const discountLevel = level(kpi.weighted_discount_pct, discountWarn, discountCritical);
  setText('kpiDiscount', fmtPct(kpi.weighted_discount_pct));
  renderPolicyMeter('kpiDiscountMeter', kpi.weighted_discount_pct, discountWarn, discountCritical, discountLevel);
  applyStateTag('kpiDiscountState', discountLevel, stateLabel(discountLevel));
  setText('kpiDiscountDetail', `${fmtCompactUsd(kpi.leakage)} of list value given away — ${thresholdGapLabel(kpi.weighted_discount_pct, discountWarn)}.`);

  const marginLevel = level(marginRiskShare, marginWarn, marginCritical);
  setText('kpiMarginRisk', fmtCompactUsd(kpi.margin_at_risk));
  renderPolicyMeter('kpiMarginRiskMeter', marginRiskShare, marginWarn, marginCritical, marginLevel);
  applyStateTag('kpiMarginRiskState', marginLevel, stateLabel(marginLevel));
  setText('kpiMarginRiskDetail', `${fmtPct(marginRiskShare)} of scoped revenue — ${thresholdGapLabel(marginRiskShare, marginWarn)}.`);

  const riskLevel = level(highRiskCount, riskWarn, riskCritical);
  setText('kpiHighRisk', fmtCount(highRiskCount));
  renderPolicyMeter('kpiHighRiskMeter', highRiskCount, riskWarn, riskCritical, riskLevel);
  applyStateTag('kpiHighRiskState', riskLevel, stateLabel(riskLevel));
  setText('kpiHighRiskDetail', `Warning line at ${fmtCount(riskWarn)} accounts, critical at ${fmtCount(riskCritical)}.`);

  return { ...kpi, high_risk_count: highRiskCount, margin_risk_share: marginRiskShare };
}

/* ---------------- verdict ---------------- */

function updateVerdict(filters, kpi, riskRows) {
  const driverRevenue = new Map();
  const actionRevenue = new Map();
  riskRows.forEach((r) => {
    const driver = r.main_risk_driver || 'unknown';
    driverRevenue.set(driver, (driverRevenue.get(driver) || 0) + (Number(r.filtered_revenue) || 0));
    const action = r.recommended_action || 'unclassified';
    actionRevenue.set(action, (actionRevenue.get(action) || 0) + (Number(r.filtered_revenue) || 0));
  });
  const [topDriver, topDriverRevenue] = topEntry(driverRevenue);
  const [topAction, topActionRevenue] = topEntry(actionRevenue);
  const topDriverLabel = scoreComponentLabel(topDriver || 'mixed');
  const topActionLabel = topAction ? titleCaseLabel(topAction) : 'Monitor only';

  const posture = resolvePosture(kpi);
  const verdictEl = document.getElementById('verdictBlock');
  if (verdictEl) verdictEl.className = `verdict verdict-${posture.level}`;
  const postureEl = document.getElementById('posturePill');
  if (postureEl) postureEl.className = `posture posture-${posture.level}`;
  setText('postureLabel', posture.label);

  setText('heroLeakage', fmtCompactUsd(kpi.leakage));
  setText('heroCallout',
    `${fmtPct(kpi.weighted_discount_pct)} of ${fmtCompactUsd(kpi.list_revenue)} in list value never reached the invoice. ` +
    `Of the ${fmtCompactUsd(kpi.net_revenue)} that did, ${fmtCompactUsd(kpi.margin_at_risk)} sits in the margin-risk zone. ${posture.narrative}`);

  setText('decisionMatter', fmtCompactUsd(kpi.margin_at_risk));
  setText('decisionMatterNote', `${fmtPct(kpi.margin_risk_share || 0)} of scoped revenue, across ${fmtCount(kpi.high_risk_count || 0)} high-risk accounts`);
  setText('decisionCritical', topDriverLabel);
  setText('decisionCriticalNote', `${fmtCompactUsd(topDriverRevenue)} of reviewed revenue traces to this driver`);
  setText('decisionAction', topActionLabel);
  setText('decisionActionNote', `${fmtCompactUsd(topActionRevenue)} of reviewed revenue waiting on this action`);
}

/* ---------------- charts ---------------- */

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
    container.innerHTML = '<p class="answer">No data in the current scope.</p>';
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

function updateBridgeChart(kpi) {
  const palette = getThemePalette();
  const list = Number(kpi.list_revenue) || 0;
  const leakage = Number(kpi.leakage) || 0;
  const net = Number(kpi.net_revenue) || 0;
  const exposed = Number(kpi.margin_at_risk) || 0;
  const protectedRevenue = Math.max(net - exposed, 0);

  // List less leakage equals net by construction; carry levels chain the bars.
  const rows = [
    { label: 'List revenue', short: 'List', range: [0, list], carry: list, total: true, color: palette.graphite, tag: fmtCompactUsd(list) },
    { label: 'Discount given', short: 'Discount', range: [net, list], carry: net, total: false, color: palette.warn, tag: `−${fmtCompactUsd(leakage)}` },
    { label: 'Net revenue', short: 'Net', range: [0, net], carry: net, total: true, color: palette.graphite, tag: fmtCompactUsd(net) },
    { label: 'Margin at risk', short: 'At risk', range: [protectedRevenue, net], carry: protectedRevenue, total: false, color: palette.critical, tag: `−${fmtCompactUsd(exposed)}` },
    { label: 'Protected revenue', short: 'Protected', range: [0, protectedRevenue], carry: null, total: true, color: palette.graphite, tag: fmtCompactUsd(protectedRevenue) }
  ];

  setText('bridgeChartAnswer', list > 0
    ? `${fmtCompactUsd(leakage)} of list value is given away as discount and ${fmtCompactUsd(exposed)} of what remains sits in the margin-risk zone, leaving ${fmtCompactUsd(protectedRevenue)} protected.`
    : 'No priced revenue in the current scope.');

  renderChartDataTable('bridgeChartData', rows.map((r) => ({
    step: r.label,
    value: r.total ? r.range[1] : -(Math.abs(r.range[1] - r.range[0])),
    kind: r.total ? 'Total' : 'Reduction'
  })), [
    { key: 'step', label: 'Step' },
    { key: 'kind', label: 'Kind' },
    { key: 'value', label: 'Value', format: (v) => fmtCurrency(v) }
  ]);

  makeOrUpdateChart('bridgeChart', {
    type: 'bar',
    data: {
      labels: rows.map((r) => r.label),
      datasets: [{
        label: 'Value',
        data: rows.map((r) => r.range),
        backgroundColor: rows.map((r) => r.color),
        borderRadius: (ctx) => rows[ctx.dataIndex] && rows[ctx.dataIndex].total
          ? { topLeft: 4, topRight: 4, bottomLeft: 0, bottomRight: 0 }
          : 4,
        borderSkipped: false,
        maxBarThickness: 76
      }]
    },
    options: {
      responsive: true,
      layout: { padding: { top: 24 } },
      plugins: {
        legend: { display: false },
        tooltip: {
          callbacks: {
            label: (ctx) => {
              const row = rows[ctx.dataIndex];
              if (!row) return '';
              const magnitude = Math.abs(row.range[1] - row.range[0]);
              return row.total
                ? `${row.label}: ${fmtCurrency(magnitude)}`
                : `${row.label}: −${fmtCurrency(magnitude)}`;
            }
          }
        },
        bridgeDecor: {
          rows,
          connector: palette.axis,
          label: palette.ink,
          labelMuted: palette.axisText
        },
        crosshair: { color: '' },
        policyLines: { lines: null },
        barTipLabels: { labels: null }
      },
      scales: {
        x: {
          ticks: {
            color: palette.axisText, font: { size: 11.5 }, autoSkip: false,
            maxRotation: 0,
            callback(_, i) {
              const row = rows[i];
              if (!row) return '';
              return this.chart.width < 560 ? row.short : row.label;
            }
          },
          grid: { display: false },
          border: { color: palette.axis }
        },
        y: {
          beginAtZero: true,
          ticks: { maxTicksLimit: 6, color: palette.axisText, callback: (v) => fmtAxisUsd(v) },
          grid: { color: palette.grid },
          border: { display: false }
        }
      }
    }
  });
}

function updateTrendChart(filters) {
  const palette = getThemePalette();
  const buckets = new Map();
  DATA.pricingAggRows.forEach((row) => {
    if (!matchesBaseRow(row, filters) || !matchesPeriod(row, filters)) return;
    const month = row.order_month;
    if (!buckets.has(month)) buckets.set(month, { list_revenue: 0, discount_weighted_num: 0 });
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
    setText('trendChartAnswer', 'No priced revenue in the current scope.');
  } else if (monthly.length === 1) {
    setText('trendChartAnswer', `${fmtMonth(monthly[0].month)} weighted discount is ${fmtPct(monthly[0].weighted_discount_pct)}.`);
  } else {
    const latest = monthly[monthly.length - 1];
    const prior = monthly[monthly.length - 2];
    const deltaPts = (latest.weighted_discount_pct - prior.weighted_discount_pct) * 100;
    const direction = deltaPts >= 0 ? 'up' : 'down';
    setText('trendChartAnswer', `${fmtMonth(latest.month)} closed at ${fmtPct(latest.weighted_discount_pct)}, ${direction} ${Math.abs(deltaPts).toFixed(1)} pts on the prior month.`);
  }
  renderChartDataTable('trendChartData', [...monthly].reverse(), [
    { key: 'month', label: 'Month', format: fmtMonth },
    { key: 'weighted_discount_pct', label: 'Weighted discount', format: (v) => fmtPct(v) }
  ]);

  const warnPct = Number(KPI_POLICY.weighted_discount_warn ?? 0.14) * 100;
  const criticalPct = Number(KPI_POLICY.weighted_discount_critical ?? 0.20) * 100;
  const values = monthly.map((r) => r.weighted_discount_pct * 100);
  const dataMax = values.length ? Math.max(...values) : 0;
  const dataMin = values.length ? Math.min(...values) : 0;
  const lastIndex = monthly.length - 1;

  /* The line is a rate, so it needs no zero baseline — but the axis must always
     frame both policy lines, otherwise "how close are we?" has no anchor. */
  const axisMin = Math.max(0, Math.floor(Math.min(dataMin, warnPct) - 2));
  const axisMax = Math.ceil(Math.max(dataMax, criticalPct) + 2);

  makeOrUpdateChart('trendChart', {
    type: 'line',
    data: {
      labels: monthly.map((r) => fmtMonth(r.month)),
      datasets: [{
        label: 'Weighted discount',
        data: monthly.map((r) => r.weighted_discount_pct * 100),
        borderColor: palette.accent,
        borderWidth: 2,
        borderJoinStyle: 'round',
        borderCapStyle: 'round',
        tension: 0.22,
        fill: false,
        pointRadius: (ctx) => ctx.dataIndex === lastIndex ? 4 : 0,
        pointHoverRadius: 5,
        pointHitRadius: 14,
        pointBackgroundColor: palette.accent,
        pointBorderColor: palette.surface,
        pointBorderWidth: 2
      }]
    },
    options: {
      responsive: true,
      interaction: { mode: 'index', intersect: false },
      layout: { padding: { top: 8 } },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (ctx) => `Weighted discount: ${Number(ctx.raw).toFixed(1)}%` } },
        crosshair: { color: palette.axis },
        policyLines: {
          lines: [
            { value: warnPct, color: palette.warn, label: `Warn ${warnPct.toFixed(0)}%` },
            { value: criticalPct, color: palette.critical, label: `Critical ${criticalPct.toFixed(0)}%` }
          ],
          zoneFrom: criticalPct,
          zoneColor: palette.criticalWash,
          labelColor: palette.axisText
        },
        bridgeDecor: { rows: null },
        barTipLabels: { labels: null }
      },
      scales: {
        x: {
          ticks: { autoSkip: true, maxTicksLimit: 8, maxRotation: 0, color: palette.axisText },
          grid: { display: false },
          border: { color: palette.axis }
        },
        y: {
          min: axisMin,
          max: axisMax,
          ticks: { maxTicksLimit: 5, color: palette.axisText, callback: (v) => `${Number(v).toFixed(0)}%` },
          grid: { color: palette.grid },
          border: { display: false }
        }
      }
    }
  });
}

function rankedBarChart(id, rows, opts) {
  const palette = getThemePalette();
  makeOrUpdateChart(id, {
    type: 'bar',
    data: {
      labels: rows.map((r) => r.label),
      datasets: [{
        label: opts.seriesLabel,
        data: rows.map((r) => r.value),
        backgroundColor: opts.color,
        borderRadius: opts.horizontal
          ? { topRight: 4, bottomRight: 4, topLeft: 0, bottomLeft: 0 }
          : { topLeft: 4, topRight: 4, bottomLeft: 0, bottomRight: 0 },
        borderSkipped: false,
        maxBarThickness: 24
      }]
    },
    options: {
      responsive: true,
      indexAxis: opts.horizontal ? 'y' : 'x',
      layout: { padding: opts.horizontal ? { right: 72 } : { top: 22 } },
      plugins: {
        legend: { display: false },
        tooltip: { callbacks: { label: (ctx) => `${opts.seriesLabel}: ${opts.fmt(ctx.raw)}` } },
        barTipLabels: { labels: rows.map((r) => opts.fmt(r.value)), color: palette.ink2 },
        crosshair: { color: '' },
        policyLines: { lines: null },
        bridgeDecor: { rows: null }
      },
      scales: opts.horizontal
        ? {
            y: { ticks: { autoSkip: false, color: palette.axisText, font: { size: 11.5 },
                   callback: (_, i) => compactLabel(rows[i] ? rows[i].label : '', 24) },
                 grid: { display: false }, border: { color: palette.axis } },
            x: { display: false, beginAtZero: true, grace: '6%' }
          }
        : {
            x: { ticks: { color: palette.axisText, font: { size: 11.5 }, maxRotation: 0, autoSkip: false,
                   callback: (_, i) => compactLabel(rows[i] ? rows[i].label : '', 14) },
                 grid: { display: false }, border: { color: palette.axis } },
            y: { display: false, beginAtZero: true, grace: '12%' }
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
    if (!grouped.has(key)) grouped.set(key, { discount_weighted_num: 0, line_list_revenue: 0 });
    const acc = grouped.get(key);
    acc.discount_weighted_num += Number(row.discount_weighted_num) || 0;
    acc.line_list_revenue += Number(row.line_list_revenue) || 0;
  });

  const rows = [...grouped.entries()]
    .map(([segment, v]) => ({
      label: segment,
      value: v.line_list_revenue > 0 ? (v.discount_weighted_num / v.line_list_revenue) * 100 : 0
    }))
    .sort((a, b) => b.value - a.value);

  const top = rows[0];
  setText('segmentChartAnswer', top
    ? `${top.label} runs the deepest discount at ${top.value.toFixed(1)}% of list.`
    : 'No segment has priced revenue in the current scope.');
  renderChartDataTable('segmentChartData', rows, [
    { key: 'label', label: 'Segment' },
    { key: 'value', label: 'Weighted discount', format: (v) => `${Number(v).toFixed(1)}%` }
  ]);

  rankedBarChart('segmentChart', rows, {
    seriesLabel: 'Weighted discount',
    color: palette.accent,
    fmt: (v) => `${Number(v).toFixed(1)}%`,
    horizontal: false
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
    grouped.set(row.region, (grouped.get(row.region) || 0) + (Number(row.margin_risk_revenue) || 0));
  });

  const rows = [...grouped.entries()]
    .map(([region, value]) => ({ label: region, value }))
    .sort((a, b) => b.value - a.value);

  const top = rows[0];
  setText('regionRiskChartAnswer', top
    ? `${top.label} carries the largest exposure at ${fmtCompactUsd(top.value)}.`
    : 'No regional exposure in the current scope.');
  renderChartDataTable('regionRiskChartData', rows, [
    { key: 'label', label: 'Region' },
    { key: 'value', label: 'Margin at risk', format: (v) => fmtCurrency(v) }
  ]);

  rankedBarChart('regionRiskChart', rows, {
    seriesLabel: 'Margin at risk',
    color: palette.accent,
    fmt: (v) => fmtCompactUsd(v),
    horizontal: false
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
    grouped.set(key, (grouped.get(key) || 0) + (Number(row.filtered_revenue) || 0));
  });

  const rows = [...grouped.entries()]
    .map(([label, value]) => ({ label: titleCaseLabel(label), value }))
    .sort((a, b) => b.value - a.value);
  const displayRows = collapseTail(rows, 6);
  const top = rows[0];

  setText('actionChartAnswer', top
    ? `${top.label} is the largest bucket at ${fmtCompactUsd(top.value)} of reviewed revenue.`
    : 'No intervention workload in the current scope.');
  renderChartDataTable('actionChartData', displayRows, [
    { key: 'label', label: 'Recommended action' },
    { key: 'value', label: 'Revenue in scope', format: (v) => fmtCurrency(v) }
  ]);

  rankedBarChart('actionChart', displayRows, {
    seriesLabel: 'Revenue in scope',
    color: palette.accent,
    fmt: (v) => fmtCompactUsd(v),
    horizontal: true
  });
}

/* ---------------- queue table ---------------- */

function tierChip(tier) {
  const cls = { Critical: 'tier-critical', High: 'tier-high', Medium: 'tier-medium', Low: 'tier-low' }[tier] || '';
  return `<span class="tier-chip ${cls}"><i></i>${escapeHtml(tier || 'Unknown')}</span>`;
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
    if (typeof av === 'number' && typeof bv === 'number') return (av - bv) * dir;
    return String(av).localeCompare(String(bv)) * dir;
  });
}

function updateTableSortIndicators() {
  document.querySelectorAll('#riskTable thead th[aria-sort]').forEach((th) => {
    const button = th.querySelector('.sort-button');
    const key = button ? button.getAttribute('data-key') : null;
    th.setAttribute('aria-sort', key === tableState.key
      ? (tableState.dir === 'asc' ? 'ascending' : 'descending')
      : 'none');
  });
}

function renderTable(riskRows) {
  const sortedRows = sortRows(riskRows);
  const displayedRows = sortedRows.slice(0, 120);
  updateTableSortIndicators();

  setText('tableCount', `${displayedRows.length} of ${riskRows.length} accounts`);
  setText('tableSortMeta', `Sorted by ${sortLabel(tableState.key)}, ${tableState.dir === 'asc' ? 'ascending' : 'descending'}.`);

  const tbody = document.querySelector('#riskTable tbody');
  if (!displayedRows.length) {
    tbody.innerHTML = '<tr><td class="empty-cell" colspan="10">No account in this scope meets the review threshold. Widen the scope, or read this as a clean slice.</td></tr>';
    return;
  }

  tbody.innerHTML = displayedRows.map((r, index) => `
    <tr>
      <td class="rank-col">${index + 1}</td>
      <td class="id-col">${escapeHtml(r.customer_id)}</td>
      <td>${escapeHtml(r.segment)}</td>
      <td>${escapeHtml(r.region)}</td>
      <td class="num">${fmtCurrency(r.filtered_revenue)}</td>
      <td class="num">${fmtPct(r.filtered_avg_discount)}</td>
      <td class="num">${(Number(r.governance_priority_score) || 0).toFixed(1)}</td>
      <td>${tierChip(r.risk_tier)}</td>
      <td>${escapeHtml(scoreComponentLabel(r.main_risk_driver))}</td>
      <td>${escapeHtml(titleCaseLabel(r.recommended_action || 'Unclassified'))}</td>
    </tr>
  `).join('');
}

/* ---------------- wiring ---------------- */

function setPeriodOptions() {
  const months = DATA.filterOptions.order_month || [];
  populateSelect(filterEls.period_start, months);
  populateSelect(filterEls.period_end, months);
  if (months.length > 0) {
    filterEls.period_start.value = months[0];
    filterEls.period_end.value = months[months.length - 1];
  }
}

function updateCoverageMeta(filters) {
  setText('coverageMeta',
    `Commercial window ${DATA.meta.coverage_start} to ${DATA.meta.coverage_end} · viewing ${fmtMonth(filters.period_start)} to ${fmtMonth(filters.period_end)}`);
}

function updateControlsMeta(filters) {
  const readable = (val, label) => val === ALL ? `all ${label}` : val;
  setText('controlsMeta',
    `${readable(filters.segment, 'segments')} · ${readable(filters.region, 'regions')} · ${readable(filters.category, 'categories')} · ${readable(filters.sales_channel, 'channels')} · ${fmtMonth(filters.period_start)}–${fmtMonth(filters.period_end)}`);
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

  updateCoverageMeta(filters);
  updateControlsMeta(filters);
  const kpi = updateKpis(filters, riskRows);
  updateVerdict(filters, kpi, riskRows);
  updateBridgeChart(kpi);
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
      applyTheme(current === 'dark' ? 'light' : 'dark', true);
      updateAll();
    });
  }
  if (printBtnEl) printBtnEl.addEventListener('click', () => window.print());

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
