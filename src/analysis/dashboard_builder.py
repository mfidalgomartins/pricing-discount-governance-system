from __future__ import annotations

import json
from itertools import combinations
from pathlib import Path
from typing import Dict

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
      --bg: #eef3fb;
      --bg-radial: #d4e1f6;
      --surface: #ffffff;
      --surface-soft: #f3f7fd;
      --surface-soft-alt: #eaf1fb;
      --ink: #0f172a;
      --muted: #51647c;
      --border: #d7e1ef;
      --hero-start: #0f1f38;
      --hero-end: #1e426a;
      --hero-ink: #edf4ff;
      --hero-muted: #c4d7f3;
      --hero-chip-bg: rgba(7, 16, 31, 0.34);
      --hero-chip-border: rgba(208, 224, 248, 0.2);
      --input-bg: #ffffff;
      --input-border: #c6d2e3;
      --grid: #d8e3f2;
      --row-hover: #eff5fd;
      --row-alt: #f8fbff;
      --chart-trend-line: #0f766e;
      --chart-trend-fill: rgba(15, 118, 110, 0.12);
      --chart-segment: #0f7bb7;
      --chart-region: #d97706;
      --chart-action: #334155;
      --shadow: 0 18px 46px rgba(15, 23, 42, 0.08);
      --shadow-soft: 0 8px 22px rgba(15, 23, 42, 0.05);
      --radius: 18px;
      --radius-sm: 12px;
      --focus-ring: 0 0 0 3px rgba(14, 165, 233, 0.28);
      --ok: #0f766e;
      --warn: #a16207;
      --critical: #b91c1c;
      --neutral: #1d4ed8;
      --chip-bg: #edf3fd;
      --chip-border: #ccd7e6;
      --tone-ok-bg: #ebfbf6;
      --tone-ok-border: #9ce7d6;
      --tone-warn-bg: #fff7e8;
      --tone-warn-border: #f8d597;
      --tone-critical-bg: #fff0f1;
      --tone-critical-border: #f9b1b6;
      --tone-neutral-bg: #edf3ff;
      --tone-neutral-border: #c6d8ff;
      --table-head-bg: rgba(243, 247, 253, 0.96);
    }

    [data-theme="dark"] {
      color-scheme: dark;
      --bg: #08111d;
      --bg-radial: #12253f;
      --surface: #0f1a2c;
      --surface-soft: #132136;
      --surface-soft-alt: #18273f;
      --ink: #e7eef9;
      --muted: #9fb4cc;
      --border: #2a3b56;
      --hero-start: #0f182b;
      --hero-end: #1b3557;
      --hero-ink: #f0f5ff;
      --hero-muted: #c0d2ea;
      --hero-chip-bg: rgba(7, 12, 21, 0.72);
      --hero-chip-border: rgba(159, 180, 204, 0.3);
      --input-bg: #0d182a;
      --input-border: #2e4563;
      --grid: #293a55;
      --row-hover: #15263d;
      --row-alt: #132034;
      --chart-trend-line: #34d399;
      --chart-trend-fill: rgba(52, 211, 153, 0.14);
      --chart-segment: #38bdf8;
      --chart-region: #fb923c;
      --chart-action: #cbd5e1;
      --shadow: 0 16px 42px rgba(0, 0, 0, 0.34);
      --shadow-soft: 0 8px 22px rgba(0, 0, 0, 0.24);
      --focus-ring: 0 0 0 3px rgba(56, 189, 248, 0.24);
      --ok: #34d399;
      --warn: #fbbf24;
      --critical: #f87171;
      --neutral: #93c5fd;
      --chip-bg: #14253d;
      --chip-border: #304662;
      --tone-ok-bg: #14352a;
      --tone-ok-border: #1f7f66;
      --tone-warn-bg: #3f2f13;
      --tone-warn-border: #8e661f;
      --tone-critical-bg: #3e1f28;
      --tone-critical-border: #8b3442;
      --tone-neutral-bg: #1a2c50;
      --tone-neutral-border: #395c9b;
      --table-head-bg: rgba(19, 33, 54, 0.96);
    }

    * { box-sizing: border-box; }

    body {
      margin: 0;
      background:
        radial-gradient(circle at 16% -6%, var(--bg-radial) 0, transparent 40%),
        radial-gradient(circle at 88% -10%, var(--bg-radial) 0, transparent 32%),
        var(--bg);
      color: var(--ink);
      font-family: \"IBM Plex Sans\", \"Avenir Next\", \"Segoe UI\", sans-serif;
      line-height: 1.5;
      -webkit-font-smoothing: antialiased;
      text-rendering: optimizeLegibility;
      transition: background-color 0.2s ease, color 0.2s ease;
    }

    .page {
      max-width: 1520px;
      margin: 0 auto;
      padding: 26px clamp(14px, 2.6vw, 36px) 40px;
      display: grid;
      gap: 18px;
    }

    .hero {
      background: linear-gradient(138deg, var(--hero-start), var(--hero-end));
      border-radius: var(--radius);
      color: var(--hero-ink);
      box-shadow: var(--shadow);
      padding: 24px clamp(18px, 2.5vw, 34px);
    }

    .hero-grid {
      display: grid;
      grid-template-columns: minmax(0, 1.4fr) minmax(300px, 0.92fr);
      gap: 18px;
      align-items: stretch;
    }

    .hero-copy {
      display: grid;
      gap: 14px;
      min-width: 0;
    }

    .hero-top {
      display: flex;
      justify-content: space-between;
      align-items: flex-start;
      gap: 14px;
      flex-wrap: wrap;
    }

    .hero h1 {
      margin: 0;
      font-size: clamp(1.82rem, 2.55vw, 2.48rem);
      line-height: 1.14;
      letter-spacing: 0.012em;
      max-width: 920px;
    }

    .hero-subtitle {
      margin: 0;
      color: var(--hero-muted);
      max-width: 900px;
      font-size: clamp(1rem, 1.18vw, 1.08rem);
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
      padding: 5px 10px;
      white-space: nowrap;
    }

    .hero-callout {
      margin: 0;
      max-width: 900px;
      font-size: 0.95rem;
      line-height: 1.55;
      color: var(--hero-ink);
    }

    .hero-rail {
      background: rgba(7, 16, 31, 0.18);
      border: 1px solid var(--hero-chip-border);
      border-radius: calc(var(--radius) - 2px);
      padding: 14px;
      display: grid;
      gap: 12px;
      min-width: 0;
      align-content: start;
    }

    .hero-status {
      display: grid;
      gap: 6px;
      padding: 12px 14px;
      border-radius: 14px;
      border: 1px solid transparent;
      background: rgba(8, 18, 35, 0.28);
    }

    .hero-status-label,
    .summary-label,
    .insight-label,
    .chart-kicker,
    .section-kicker,
    .table-stat-label {
      display: inline-block;
      font-size: 0.74rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }

    .hero-status-label {
      color: var(--hero-muted);
    }

    .hero-status-value {
      font-size: 1.28rem;
      font-weight: 700;
      line-height: 1.2;
    }

    .hero-status-note {
      font-size: 0.82rem;
      color: var(--hero-muted);
      line-height: 1.45;
    }

    .hero-status.hero-status-ok {
      background: rgba(15, 118, 110, 0.16);
      border-color: rgba(52, 211, 153, 0.22);
    }

    .hero-status.hero-status-warn {
      background: rgba(161, 98, 7, 0.18);
      border-color: rgba(251, 191, 36, 0.24);
    }

    .hero-status.hero-status-critical {
      background: rgba(185, 28, 28, 0.16);
      border-color: rgba(248, 113, 113, 0.22);
    }

    .hero-summary-grid {
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }

    .summary-card {
      border-radius: 14px;
      padding: 12px 13px;
      background: rgba(8, 18, 35, 0.18);
      border: 1px solid var(--hero-chip-border);
      display: grid;
      gap: 4px;
      min-width: 0;
    }

    .summary-label {
      color: var(--hero-muted);
    }

    .summary-value {
      font-size: 1.15rem;
      font-weight: 700;
      line-height: 1.2;
      color: var(--hero-ink);
      overflow-wrap: anywhere;
    }

    .summary-note {
      font-size: 0.8rem;
      color: var(--hero-muted);
      line-height: 1.4;
    }

    .hero-actions {
      display: flex;
      gap: 8px;
      align-items: center;
      flex-wrap: wrap;
    }

    .theme-toggle,
    .print-btn {
      border: 1px solid var(--hero-chip-border);
      background: var(--hero-chip-bg);
      color: var(--hero-ink);
      min-height: 36px;
      padding: 0 14px;
      border-radius: 999px;
      font-size: 0.8rem;
      font-weight: 700;
      letter-spacing: 0.01em;
      cursor: pointer;
    }

    .theme-toggle:hover,
    .print-btn:hover { filter: brightness(1.08); }
    .theme-toggle:focus-visible,
    .print-btn:focus-visible {
      outline: none;
      box-shadow: var(--focus-ring);
    }

    .section-head {
      display: flex;
      justify-content: space-between;
      gap: 14px;
      align-items: baseline;
      flex-wrap: wrap;
      padding: 2px 2px 0;
    }

    .section-head h2 {
      margin: 0;
      font-size: 1.12rem;
      letter-spacing: 0.012em;
    }

    .section-head p {
      margin: 0;
      color: var(--muted);
      font-size: 0.84rem;
      max-width: 760px;
    }

    .controls-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      padding: 12px 14px 0;
      flex-wrap: wrap;
    }

    .controls-meta {
      margin: 0;
      font-size: 0.81rem;
      color: var(--muted);
    }

    .reset-btn {
      height: 36px;
      border-radius: 999px;
      border: 1px solid var(--input-border);
      background: var(--input-bg);
      color: var(--ink);
      font-size: 0.79rem;
      font-weight: 700;
      padding: 0 13px;
      cursor: pointer;
    }
    .reset-btn:hover { filter: brightness(0.98); }
    .reset-btn:focus-visible {
      outline: none;
      box-shadow: var(--focus-ring);
      border-color: transparent;
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

    .filters-panel {
      overflow: hidden;
    }

    .filters {
      padding: 14px 14px 16px;
      display: grid;
      grid-template-columns: repeat(6, minmax(0, 1fr));
      gap: 11px;
      align-items: end;
    }

    .field { min-width: 0; }

    .field label {
      display: block;
      margin-bottom: 7px;
      font-size: 0.76rem;
      font-weight: 700;
      text-transform: uppercase;
      letter-spacing: 0.035em;
      color: var(--muted);
    }

    .field select {
      width: 100%;
      min-width: 0;
      height: 41px;
      border-radius: var(--radius-sm);
      border: 1px solid var(--input-border);
      background: var(--input-bg);
      color: var(--ink);
      font-size: 0.9rem;
      padding: 0 11px;
    }
    .field select:focus-visible {
      outline: none;
      box-shadow: var(--focus-ring);
      border-color: transparent;
    }

    .kpis {
      display: grid;
      gap: 15px;
      grid-template-columns: repeat(4, minmax(0, 1fr));
    }

    .kpi {
      padding: 16px 16px 15px;
      display: grid;
      gap: 8px;
      min-height: 124px;
      border-top: 3px solid var(--border);
      position: relative;
    }

    .kpi.kpi-critical { border-top-color: var(--critical); }
    .kpi.kpi-warn { border-top-color: var(--warn); }
    .kpi.kpi-ok { border-top-color: var(--ok); }
    .kpi.kpi-neutral { border-top-color: var(--neutral); }

    .kpi-title {
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      color: var(--muted);
      font-weight: 700;
      margin: 0;
    }

    .kpi-head {
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 10px;
    }

    .kpi-state {
      display: inline-flex;
      align-items: center;
      border-radius: 999px;
      border: 1px solid transparent;
      padding: 2px 8px;
      font-size: 0.69rem;
      font-weight: 700;
      white-space: nowrap;
    }

    .kpi-state-ok {
      background: var(--tone-ok-bg);
      border-color: var(--tone-ok-border);
      color: var(--ok);
    }

    .kpi-state-warn {
      background: var(--tone-warn-bg);
      border-color: var(--tone-warn-border);
      color: var(--warn);
    }

    .kpi-state-critical {
      background: var(--tone-critical-bg);
      border-color: var(--tone-critical-border);
      color: var(--critical);
    }

    .kpi-state-neutral {
      background: var(--tone-neutral-bg);
      border-color: var(--tone-neutral-border);
      color: var(--neutral);
    }

    .kpi-value {
      margin: 0;
      font-size: clamp(1.36rem, 2.12vw, 2.24rem);
      font-weight: 700;
      overflow-wrap: anywhere;
      line-height: 1.2;
    }

    .kpi-sub {
      margin: 0;
      font-size: 0.77rem;
      color: var(--muted);
    }

    .insight-strip {
      padding: 15px 16px;
      display: grid;
      gap: 10px;
      border-left: 4px solid var(--neutral);
      background: var(--surface-soft);
    }

    .insight-strip.insight-critical { border-left-color: var(--critical); }
    .insight-strip.insight-warn { border-left-color: var(--warn); }
    .insight-strip.insight-ok { border-left-color: var(--ok); }

    .insight-main {
      margin: 0;
      font-size: 0.93rem;
      line-height: 1.45;
    }

    .insight-chips {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }

    .insight-chip {
      border: 1px solid var(--chip-border);
      background: var(--chip-bg);
      border-radius: 999px;
      padding: 4px 11px;
      font-size: 0.76rem;
      color: var(--ink);
      white-space: nowrap;
    }

    .brief-grid {
      padding: 12px;
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      gap: 10px;
    }

    .brief-card {
      background: var(--surface-soft);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 12px 13px;
      display: grid;
      gap: 6px;
      min-width: 0;
    }

    .brief-label {
      margin: 0;
      font-size: 0.72rem;
      text-transform: uppercase;
      letter-spacing: 0.035em;
      color: var(--muted);
      font-weight: 700;
    }

    .brief-value {
      margin: 0;
      font-size: clamp(1.02rem, 1.25vw, 1.24rem);
      font-weight: 700;
      line-height: 1.2;
    }

    .brief-value.brief-ok { color: var(--ok); }
    .brief-value.brief-warn { color: var(--warn); }
    .brief-value.brief-critical { color: var(--critical); }

    .brief-sub {
      margin: 0;
      font-size: 0.76rem;
      color: var(--muted);
      line-height: 1.35;
    }

    .charts {
      display: grid;
      gap: 15px;
      grid-template-columns: repeat(2, minmax(0, 1fr));
    }

    .chart-card {
      padding: 15px 15px 13px;
      display: grid;
      gap: 9px;
      min-width: 0;
    }

    .chart-head {
      display: grid;
      gap: 4px;
    }

    .chart-card h3 {
      margin: 0;
      font-size: 1.02rem;
      line-height: 1.25;
      max-width: 92%;
    }

    .chart-card p {
      margin: 0;
      font-size: 0.8rem;
      color: var(--muted);
      max-width: 96%;
    }

    .chart-wrap {
      position: relative;
      width: 100%;
      height: 330px;
      min-height: 300px;
    }
    .chart-wrap canvas {
      width: 100% !important;
      height: 100% !important;
    }

    .table-head {
      padding: 14px 16px 13px;
      border-bottom: 1px solid var(--border);
      background: var(--surface-soft);
    }

    .table-head h3 {
      margin: 0;
      font-size: 1.03rem;
    }

    .table-head p {
      margin: 5px 0 0 0;
      font-size: 0.8rem;
      color: var(--muted);
    }

    .table-wrap {
      overflow: auto;
      max-height: 520px;
    }

    table {
      width: 100%;
      min-width: 940px;
      border-collapse: collapse;
    }

    th,
    td {
      padding: 10px 12px;
      border-bottom: 1px solid var(--border);
      text-align: left;
      vertical-align: top;
      font-size: 0.84rem;
    }

    th {
      position: sticky;
      top: 0;
      z-index: 2;
      background: var(--surface-soft);
      cursor: pointer;
      user-select: none;
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.03em;
      white-space: nowrap;
    }

    th::after {
      content: '↕';
      margin-left: 6px;
      color: var(--muted);
      font-size: 0.68rem;
      opacity: 0.5;
    }

    th.sort-asc::after {
      content: '↑';
      opacity: 1;
    }

    th.sort-desc::after {
      content: '↓';
      opacity: 1;
    }

    #riskTable th:first-child,
    #riskTable td:first-child {
      position: sticky;
      left: 0;
    }

    #riskTable th:first-child {
      z-index: 3;
      background: var(--surface-soft);
    }

    #riskTable td:first-child {
      background: var(--surface);
      font-weight: 700;
      min-width: 128px;
    }

    tbody tr:nth-child(even) td {
      background: var(--row-alt);
    }

    tbody tr:hover td {
      background: var(--row-hover);
    }

    tbody tr:hover td:first-child {
      background: var(--row-hover);
    }

    .action-cell {
      max-width: 320px;
      min-width: 220px;
      white-space: normal;
      line-height: 1.35;
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

    @media (max-width: 1220px) {
      .filters { grid-template-columns: repeat(3, minmax(0, 1fr)); }
      .kpis { grid-template-columns: repeat(2, minmax(0, 1fr)); }
      .brief-grid { grid-template-columns: 1fr; }
      .charts { grid-template-columns: 1fr; }
      .chart-wrap { height: 280px; }
    }

    @media (max-width: 720px) {
      .page {
        padding: 14px 10px 20px;
        gap: 12px;
      }

      .filters,
      .kpis {
        grid-template-columns: 1fr;
      }

      .brief-grid {
        grid-template-columns: 1fr;
      }

      .chart-wrap {
        height: 250px;
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

    @media print {
      :root,
      [data-theme="dark"] {
        --bg: #ffffff;
        --bg-radial: #ffffff;
        --surface: #ffffff;
        --surface-soft: #ffffff;
        --ink: #111827;
        --muted: #334155;
        --border: #cbd5e1;
        --grid: #e2e8f0;
        --shadow: none;
      }

      body {
        background: #ffffff !important;
        color: #111827 !important;
        -webkit-print-color-adjust: exact;
        print-color-adjust: exact;
      }

      .page {
        max-width: none;
        padding: 8mm 10mm;
        gap: 10px;
      }

      .theme-toggle,
      .print-btn,
      .reset-btn,
      .filters {
        display: none !important;
      }

      .controls-row {
        padding: 0;
      }

      .hero,
      .panel,
      .kpi,
      .brief-card,
      .chart-card,
      .table-panel {
        box-shadow: none !important;
        break-inside: avoid;
        page-break-inside: avoid;
      }

      .filters {
        grid-template-columns: repeat(3, minmax(0, 1fr));
      }

      .field select {
        appearance: none;
        border-color: var(--border);
        background: #fff;
      }

      .chart-wrap {
        height: 240px;
        min-height: 240px;
      }

      .table-wrap {
        max-height: none;
        overflow: visible;
      }

      #riskTable th:first-child,
      #riskTable td:first-child {
        position: static;
      }

      table {
        min-width: 100%;
      }

      .table-panel {
        page-break-inside: avoid;
      }
    }
  </style>
</head>
<body>
<div class=\"page\">
  <section class=\"hero\">
    <div class=\"hero-top\">
      <h1>Pricing & Discount Governance Executive Dashboard</h1>
      <div class=\"hero-actions\">
        <button id=\"themeToggle\" class=\"theme-toggle\" type=\"button\" aria-label=\"Toggle color mode\">Dark Mode</button>
        <button id=\"printBtn\" class=\"print-btn\" type=\"button\" aria-label=\"Print dashboard\">Print</button>
      </div>
    </div>
    <p>Executive view of discount intensity, margin exposure, and intervention priorities across commercial segments.</p>
    <ul class=\"hero-meta\">
      <li id=\"coverageMeta\"></li>
    </ul>
  </section>

  <div class=\"section-head\">
    <h2>Scope Controls</h2>
    <p>Filters update all KPIs, charts, and the action table with consistent governed aggregates.</p>
  </div>
  <section class=\"panel filters-panel\">
    <div class=\"controls-row\">
      <p class=\"controls-meta\" id=\"controlsMeta\">Scope: all segments, regions, categories, and channels.</p>
      <button id=\"resetFiltersBtn\" class=\"reset-btn\" type=\"button\" aria-label=\"Reset filters\">Reset Filters</button>
    </div>
    <div class=\"filters\">
      <div class=\"field\"><label for=\"segmentFilter\">Segment</label><select id=\"segmentFilter\"></select></div>
      <div class=\"field\"><label for=\"regionFilter\">Region</label><select id=\"regionFilter\"></select></div>
      <div class=\"field\"><label for=\"categoryFilter\">Product Category</label><select id=\"categoryFilter\"></select></div>
      <div class=\"field\"><label for=\"channelFilter\">Sales Channel</label><select id=\"channelFilter\"></select></div>
      <div class=\"field\"><label for=\"periodStartFilter\">Start Month</label><select id=\"periodStartFilter\"></select></div>
      <div class=\"field\"><label for=\"periodEndFilter\">End Month</label><select id=\"periodEndFilter\"></select></div>
    </div>
  </section>

  <div class=\"section-head\">
    <h2>Portfolio Health</h2>
    <p>Primary commercial quality indicators for the selected scope.</p>
  </div>
  <section class=\"kpis\">
    <article class=\"kpi kpi-neutral\" id=\"kpiRevenueCard\">
      <div class=\"kpi-head\">
        <p class=\"kpi-title\">Net Revenue In Scope</p>
        <span class=\"kpi-state kpi-state-neutral\" id=\"kpiRevenueState\">Scope</span>
      </div>
      <p class=\"kpi-value\" id=\"kpiRevenue\">-</p>
      <p class=\"kpi-sub\">Filtered commercial volume</p>
    </article>
    <article class=\"kpi kpi-warn\" id=\"kpiDiscountCard\">
      <div class=\"kpi-head\">
        <p class=\"kpi-title\">Weighted Discount</p>
        <span class=\"kpi-state kpi-state-warn\" id=\"kpiDiscountState\">Watch</span>
      </div>
      <p class=\"kpi-value\" id=\"kpiDiscount\">-</p>
      <p class=\"kpi-sub\">Revenue-weighted realized discount</p>
    </article>
    <article class=\"kpi kpi-critical\" id=\"kpiMarginRiskCard\">
      <div class=\"kpi-head\">
        <p class=\"kpi-title\">Margin At Risk</p>
        <span class=\"kpi-state kpi-state-critical\" id=\"kpiMarginRiskState\">Risk</span>
      </div>
      <p class=\"kpi-value\" id=\"kpiMarginRisk\">-</p>
      <p class=\"kpi-sub\">High-discount and low-margin proxy overlap</p>
    </article>
    <article class=\"kpi kpi-warn\" id=\"kpiHighRiskCard\">
      <div class=\"kpi-head\">
        <p class=\"kpi-title\">High-Risk Customers</p>
        <span class=\"kpi-state kpi-state-warn\" id=\"kpiHighRiskState\">Watch</span>
      </div>
      <p class=\"kpi-value\" id=\"kpiHighRisk\">-</p>
      <p class=\"kpi-sub\">Critical and high tier in current scope</p>
    </article>
  </section>

  <section class=\"panel insight-strip\">
    <p class=\"insight-main\" id=\"insightMain\">Assessing current pricing posture...</p>
    <div class=\"insight-chips\" id=\"insightChips\"></div>
  </section>

  <section class=\"panel brief-grid\">
    <article class=\"brief-card\">
      <p class=\"brief-label\">Operating posture</p>
      <p class=\"brief-value\" id=\"briefPosture\">-</p>
      <p class=\"brief-sub\" id=\"briefPostureSub\">-</p>
    </article>
    <article class=\"brief-card\">
      <p class=\"brief-label\">Revenue under high-risk accounts</p>
      <p class=\"brief-value\" id=\"briefExposure\">-</p>
      <p class=\"brief-sub\" id=\"briefExposureSub\">-</p>
    </article>
    <article class=\"brief-card\">
      <p class=\"brief-label\">Primary intervention</p>
      <p class=\"brief-value\" id=\"briefPrimaryAction\">-</p>
      <p class=\"brief-sub\" id=\"briefPrimaryActionSub\">-</p>
    </article>
  </section>

  <div class=\"section-head\">
    <h2>Diagnostics</h2>
    <p>Trend, concentration, and governance-action views to guide intervention priorities.</p>
  </div>
  <section class=\"charts\">
    <article class=\"chart-card\">
      <div class=\"chart-head\">
        <h3>Discount Pressure Trend</h3>
        <p>Monthly weighted discount pattern for the selected commercial scope.</p>
      </div>
      <div class=\"chart-wrap\"><canvas id=\"trendChart\"></canvas></div>
    </article>

    <article class=\"chart-card\">
      <div class=\"chart-head\">
        <h3>Where Discounting Concentrates</h3>
        <p>Weighted discount comparison by segment after applying current regional, category, channel, and period filters.</p>
      </div>
      <div class=\"chart-wrap\"><canvas id=\"segmentChart\"></canvas></div>
    </article>

    <article class=\"chart-card\">
      <div class=\"chart-head\">
        <h3>Margin Exposure by Region</h3>
        <p>Absolute margin-at-risk volume by region in the selected scope.</p>
      </div>
      <div class=\"chart-wrap\"><canvas id=\"regionRiskChart\"></canvas></div>
    </article>

    <article class=\"chart-card\">
      <div class=\"chart-head\">
        <h3>Intervention Portfolio Mix</h3>
        <p>Revenue concentration by recommended intervention action to support operational sequencing.</p>
      </div>
      <div class=\"chart-wrap\"><canvas id=\"actionChart\"></canvas></div>
    </article>
  </section>

  <section class=\"table-panel\">
    <div class=\"table-head\">
      <h3>Highest-Priority Customers (Top 120 in Current Scope)</h3>
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
const POLICY = DATA.policy || {};
const KPI_POLICY = POLICY.kpi_card_thresholds || {};
const POSTURE_POLICY = POLICY.posture_thresholds || {};

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
      narrative: 'Current scope shows discount-led concentration and immediate governance intervention should be prioritized.'
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
      narrative: 'Current scope is mixed. Targeted intervention is recommended before risk concentration broadens.'
    };
  }

  return {
    level: 'ok',
    label: 'Controlled',
    narrative: 'Current scope remains within monitor range with no immediate broad intervention signal.'
  };
}

function updateKpis(filters, riskRows) {
  const kpi = aggregateScopedPricing(filters);
  const marginRiskShare = (Number(kpi.net_revenue) || 0) > 0 ? (Number(kpi.margin_at_risk) || 0) / Number(kpi.net_revenue) : 0;
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

  return { ...kpi, high_risk_count: highRiskCount, margin_risk_share: marginRiskShare };
}

function updateInsight(filters, kpi, riskRows) {
  const topDriverMap = new Map();
  riskRows.forEach((r) => {
    const d = r.main_risk_driver || 'unknown';
    topDriverMap.set(d, (topDriverMap.get(d) || 0) + (Number(r.filtered_revenue) || 0));
  });
  const topDriver = [...topDriverMap.entries()].sort((a, b) => b[1] - a[1])[0]?.[0] || 'mixed';

  const posture = resolvePosture(kpi);
  document.getElementById('insightMain').textContent = posture.narrative;
  const insightEl = document.querySelector('.insight-strip');
  if (insightEl) {
    insightEl.className = `panel insight-strip insight-${posture.level}`;
  }
  const chips = [
    `Scope: ${filters.segment === ALL ? 'All segments' : filters.segment}`,
    `Weighted discount: ${fmtPct(kpi.weighted_discount_pct || 0)}`,
    `Margin at risk share: ${fmtPct(kpi.margin_risk_share || 0)}`,
    `High-risk customers: ${(kpi.high_risk_count || 0).toLocaleString('en-US')}`,
    `Top risk driver: ${String(topDriver).replaceAll('_', ' ')}`
  ];
  document.getElementById('insightChips').innerHTML = chips.map((c) => `<span class="insight-chip">${c}</span>`).join('');
}

function updateExecutiveBrief(kpi, riskRows) {
  const posture = resolvePosture(kpi);

  const highRiskRevenue = riskRows.reduce((acc, row) => {
    if (row.risk_tier === 'High' || row.risk_tier === 'Critical') {
      return acc + (Number(row.filtered_revenue) || 0);
    }
    return acc;
  }, 0);
  const exposureShare = Number(kpi.net_revenue) > 0 ? highRiskRevenue / Number(kpi.net_revenue) : 0;

  const actionMap = new Map();
  riskRows.forEach((row) => {
    const key = row.recommended_action || 'Unclassified';
    actionMap.set(key, (actionMap.get(key) || 0) + (Number(row.filtered_revenue) || 0));
  });
  const topActionRow = [...actionMap.entries()].sort((a, b) => b[1] - a[1])[0];
  const topAction = topActionRow ? topActionRow[0] : 'No intervention needed';
  const topActionValue = topActionRow ? Number(topActionRow[1]) : 0;
  const topActionShare = Number(kpi.net_revenue) > 0 ? topActionValue / Number(kpi.net_revenue) : 0;

  const postureValueEl = document.getElementById('briefPosture');
  if (postureValueEl) {
    postureValueEl.textContent = posture.label;
    postureValueEl.className = `brief-value brief-${posture.level}`;
  }
  document.getElementById('briefPostureSub').textContent = `Weighted discount ${fmtPct(Number(kpi.weighted_discount_pct) || 0)} · Margin risk share ${fmtPct(Number(kpi.margin_risk_share) || 0)}.`;

  document.getElementById('briefExposure').textContent = fmtPct(exposureShare || 0);
  document.getElementById('briefExposureSub').textContent = `${fmtCurrency(highRiskRevenue)} is currently concentrated in high and critical risk customers.`;

  document.getElementById('briefPrimaryAction').textContent = compactLabel(topAction, 34);
  document.getElementById('briefPrimaryActionSub').textContent = `${fmtPct(topActionShare || 0)} of scoped revenue is tied to this action.`;
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
  document.querySelectorAll('#riskTable thead th[data-key]').forEach((th) => {
    const key = th.getAttribute('data-key');
    th.classList.remove('sort-asc', 'sort-desc');
    if (key === tableState.key) {
      th.classList.add(tableState.dir === 'asc' ? 'sort-asc' : 'sort-desc');
    }
  });
}

function renderTable(riskRows) {
  const sorted = sortRows(riskRows).slice(0, 120);
  const tbody = document.querySelector('#riskTable tbody');
  updateTableSortIndicators();

  tbody.innerHTML = sorted.map((r) => `
    <tr>
      <td>${escapeHtml(r.customer_id)}</td>
      <td>${escapeHtml(r.segment)}</td>
      <td>${escapeHtml(r.region)}</td>
      <td>${fmtCurrency(Number(r.filtered_revenue) || 0)}</td>
      <td>${fmtPct(Number(r.filtered_avg_discount) || 0)}</td>
      <td>${(Number(r.governance_priority_score) || 0).toFixed(1)}</td>
      <td>${tierChip(r.risk_tier)}</td>
      <td class="action-cell">${escapeHtml(r.recommended_action)}</td>
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
  updateExecutiveBrief(kpi, riskRows);
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

    return dashboard_path
