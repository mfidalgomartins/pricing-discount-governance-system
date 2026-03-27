from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict

import pandas as pd

ALL_VALUE = "All"


def _as_records(df: pd.DataFrame) -> list[dict]:
    return json.loads(df.to_json(orient="records", date_format="iso"))


def build_executive_dashboard(
    processed_tables: Dict[str, pd.DataFrame],
    dashboard_dir: Path,
) -> Path:
    dashboard_dir.mkdir(parents=True, exist_ok=True)

    pricing = processed_tables["order_item_pricing_metrics"].copy()
    risk = processed_tables["customer_risk_scores"].copy()

    pricing["order_date"] = pd.to_datetime(pricing["order_date"])
    pricing["order_month"] = pd.to_datetime(pricing["order_month"]).dt.strftime("%Y-%m")

    pricing_export = pricing[
        [
            "order_date",
            "order_month",
            "segment",
            "region",
            "category",
            "sales_channel",
            "customer_id",
            "line_revenue",
            "line_list_revenue",
            "discount_depth",
            "margin_proxy_pct",
            "high_discount_flag",
        ]
    ].copy()

    risk_export = risk[
        [
            "customer_id",
            "segment",
            "region",
            "total_revenue",
            "avg_discount_pct",
            "governance_priority_score",
            "risk_tier",
            "main_risk_driver",
            "recommended_action",
        ]
    ].copy()

    filter_options = {
        "segment": [ALL_VALUE] + sorted(pricing_export["segment"].dropna().unique().tolist()),
        "region": [ALL_VALUE] + sorted(pricing_export["region"].dropna().unique().tolist()),
        "category": [ALL_VALUE] + sorted(pricing_export["category"].dropna().unique().tolist()),
        "sales_channel": [ALL_VALUE] + sorted(pricing_export["sales_channel"].dropna().unique().tolist()),
    }

    meta = {
        "generated_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC"),
        "data_as_of": pricing["order_date"].max().strftime("%Y-%m-%d"),
        "coverage_start": pricing["order_date"].min().strftime("%Y-%m-%d"),
        "coverage_end": pricing["order_date"].max().strftime("%Y-%m-%d"),
    }

    payload = {
        "pricingRows": _as_records(pricing_export),
        "riskRows": _as_records(risk_export),
        "filterOptions": filter_options,
        "meta": meta,
    }
    data_json = json.dumps(payload, separators=(",", ":"))

    html = """<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>Pricing & Discount Governance Dashboard</title>
  <script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.3/dist/chart.umd.min.js"></script>
  <style>
    :root {
      --bg: #f5f7fb;
      --card: #ffffff;
      --ink: #0f172a;
      --muted: #475569;
      --primary: #1d4ed8;
      --danger: #dc2626;
      --warning: #d97706;
      --good: #15803d;
      --border: #dbe3ef;
    }
    * { box-sizing: border-box; }
    body { margin: 0; font-family: "Avenir Next", "Segoe UI", "Helvetica Neue", sans-serif; background: var(--bg); color: var(--ink); }
    .container { max-width: 1380px; margin: 0 auto; padding: 20px; }
    .hero { background: linear-gradient(120deg, #eaf2ff, #f8fbff); border: 1px solid var(--border); border-radius: 14px; padding: 18px 22px; }
    .hero h1 { margin: 0; font-size: 1.7rem; }
    .hero p { margin: 6px 0 0 0; color: var(--muted); }
    .meta { margin-top: 8px; color: var(--muted); font-size: 0.9rem; }
    .context-box { margin-top: 12px; background: #ffffffb3; border: 1px solid #d9e3f4; border-radius: 10px; padding: 12px; }
    .context-title { font-size: 0.86rem; font-weight: 700; color: #1e3a8a; margin: 0 0 6px 0; text-transform: uppercase; letter-spacing: 0.03em; }
    .context-text { margin: 0; font-size: 0.9rem; color: #334155; line-height: 1.45; }
    .context-list { margin: 8px 0 0 16px; color: #334155; font-size: 0.88rem; }

    .filters { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; margin: 16px 0; }
    .filter-card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 10px; }
    label { display: block; font-size: 0.83rem; color: var(--muted); margin-bottom: 6px; font-weight: 600; }
    select { width: 100%; padding: 8px; border-radius: 8px; border: 1px solid #cbd5e1; background: #fff; }

    .kpis { display: grid; grid-template-columns: repeat(auto-fit, minmax(210px, 1fr)); gap: 12px; margin-bottom: 16px; }
    .kpi { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 14px; }
    .kpi-title { color: var(--muted); font-size: 0.84rem; margin-bottom: 6px; font-weight: 600; }
    .kpi-value { font-size: 1.55rem; font-weight: 700; }

    .grid { display: grid; gap: 12px; }
    .grid.primary { grid-template-columns: repeat(auto-fit, minmax(360px, 1fr)); }
    .card { background: var(--card); border: 1px solid var(--border); border-radius: 12px; padding: 12px; }
    .card h3 { margin: 0 0 8px 0; font-size: 1rem; }
    canvas { width: 100% !important; height: 320px !important; }

    .table-wrap { margin-top: 12px; overflow: auto; border: 1px solid var(--border); border-radius: 12px; background: var(--card); }
    table { width: 100%; border-collapse: collapse; min-width: 980px; }
    th, td { border-bottom: 1px solid #e8edf5; padding: 10px; text-align: left; font-size: 0.89rem; }
    th { background: #f8fbff; position: sticky; top: 0; cursor: pointer; user-select: none; }
    tr:hover td { background: #fbfdff; }

    .footer-note { margin-top: 10px; font-size: 0.82rem; color: var(--muted); }
    @media (max-width: 880px) { canvas { height: 280px !important; } }
  </style>
</head>
<body>
<div class="container">
  <section class="hero">
    <h1>Pricing & Discount Governance Dashboard</h1>
    <p>Executive view of pricing health, discount dependency, margin risk, and governance priorities.</p>
    <div class="meta" id="metaLine"></div>
    <div class="context-box">
      <p class="context-title">Business Context</p>
      <p class="context-text">This dashboard is designed to answer one governance question: is growth coming from healthy pricing discipline, or from discount behavior that increases margin risk over time?</p>
      <ul class="context-list">
        <li>KPI cards show overall pricing health for the filtered population.</li>
        <li>Charts show where discount pressure is concentrated (time, segment, channel, action).</li>
        <li>The detail table lists the highest-priority customers for commercial intervention.</li>
      </ul>
    </div>
  </section>

  <section class="filters">
    <div class="filter-card"><label for="segmentFilter">Segment</label><select id="segmentFilter"></select></div>
    <div class="filter-card"><label for="regionFilter">Region</label><select id="regionFilter"></select></div>
    <div class="filter-card"><label for="categoryFilter">Product Category</label><select id="categoryFilter"></select></div>
    <div class="filter-card"><label for="channelFilter">Sales Channel</label><select id="channelFilter"></select></div>
  </section>

  <section class="kpis">
    <div class="kpi"><div class="kpi-title">Net Revenue</div><div class="kpi-value" id="kpiRevenue">-</div></div>
    <div class="kpi"><div class="kpi-title">Average Discount</div><div class="kpi-value" id="kpiDiscount">-</div></div>
    <div class="kpi"><div class="kpi-title">Margin at Risk</div><div class="kpi-value" id="kpiMarginRisk">-</div></div>
    <div class="kpi"><div class="kpi-title">High-Risk Customer Count</div><div class="kpi-value" id="kpiHighRisk">-</div></div>
  </section>

  <section class="grid primary">
    <div class="card"><h3>Discount Trend Over Time</h3><canvas id="discountTrendChart"></canvas></div>
    <div class="card"><h3>Discount by Segment</h3><canvas id="discountBySegmentChart"></canvas></div>
    <div class="card"><h3>Pricing Inconsistency by Channel</h3><canvas id="inconsistencyChart"></canvas></div>
    <div class="card"><h3>Revenue Under High Discount</h3><canvas id="highDiscountRevenueChart"></canvas></div>
    <div class="card"><h3>Top Governance Priorities</h3><canvas id="prioritiesChart"></canvas></div>
  </section>

  <section class="table-wrap">
    <table id="riskTable">
      <thead>
        <tr>
          <th data-key="customer_id">Customer</th>
          <th data-key="segment">Segment</th>
          <th data-key="region">Region</th>
          <th data-key="total_revenue">Revenue</th>
          <th data-key="avg_discount_pct">Avg Discount</th>
          <th data-key="governance_priority_score">Governance Score</th>
          <th data-key="risk_tier">Risk Tier</th>
          <th data-key="recommended_action">Recommended Action</th>
        </tr>
      </thead>
      <tbody></tbody>
    </table>
  </section>

  <div class="footer-note">
    Self-contained dashboard with embedded data. Data as of <span id="dataAsOf"></span>.
  </div>
</div>

<script>
const DATA = __DATA_JSON__;
const ALL = "__ALL_VALUE__";

const fmtCurrency = (n) => n.toLocaleString('en-US', { style: 'currency', currency: 'USD', maximumFractionDigits: 0 });
const fmtPct = (n, digits = 1) => `${(n * 100).toFixed(digits)}%`;
const sum = (arr, key) => arr.reduce((acc, row) => acc + (+row[key] || 0), 0);

const filterEls = {
  segment: document.getElementById('segmentFilter'),
  region: document.getElementById('regionFilter'),
  category: document.getElementById('categoryFilter'),
  sales_channel: document.getElementById('channelFilter')
};

const chartRefs = {};
const tableState = { key: 'governance_priority_score', dir: 'desc' };

function populateSelect(el, values) {
  el.innerHTML = values.map(v => `<option value="${v}">${v}</option>`).join('');
}

function getFilters() {
  return {
    segment: filterEls.segment.value,
    region: filterEls.region.value,
    category: filterEls.category.value,
    sales_channel: filterEls.sales_channel.value
  };
}

function applyPricingFilters(rows, filters) {
  return rows.filter(r =>
    (filters.segment === ALL || r.segment === filters.segment) &&
    (filters.region === ALL || r.region === filters.region) &&
    (filters.category === ALL || r.category === filters.category) &&
    (filters.sales_channel === ALL || r.sales_channel === filters.sales_channel)
  );
}

function applyRiskFilters(riskRows, customerSet, filters) {
  return riskRows.filter(r =>
    customerSet.has(r.customer_id) &&
    (filters.segment === ALL || r.segment === filters.segment) &&
    (filters.region === ALL || r.region === filters.region)
  );
}

function groupBy(rows, keyFn, valueFn) {
  const out = new Map();
  rows.forEach(r => {
    const key = keyFn(r);
    const val = valueFn(r);
    if (!out.has(key)) out.set(key, []);
    out.get(key).push(val);
  });
  return out;
}

function weightedAverage(rows, valueKey, weightKey) {
  let num = 0;
  let den = 0;
  rows.forEach(r => {
    const v = +r[valueKey] || 0;
    const w = +r[weightKey] || 0;
    num += v * w;
    den += w;
  });
  return den > 0 ? num / den : 0;
}

function makeOrUpdateChart(id, config) {
  if (chartRefs[id]) {
    chartRefs[id].data = config.data;
    chartRefs[id].options = config.options;
    chartRefs[id].update();
    return;
  }
  const ctx = document.getElementById(id);
  chartRefs[id] = new Chart(ctx, config);
}

function updateKpis(pricingRows, riskRows) {
  const netRevenue = sum(pricingRows, 'line_revenue');
  const avgDiscount = weightedAverage(pricingRows, 'discount_depth', 'line_list_revenue');
  const marginAtRisk = pricingRows
    .filter(r => +r.high_discount_flag === 1 && (+r.margin_proxy_pct || 0) < 0.35)
    .reduce((a, r) => a + (+r.line_revenue || 0), 0);
  const highRiskCount = riskRows.filter(r => r.risk_tier === 'High' || r.risk_tier === 'Critical').length;

  document.getElementById('kpiRevenue').textContent = fmtCurrency(netRevenue);
  document.getElementById('kpiDiscount').textContent = fmtPct(avgDiscount);
  document.getElementById('kpiMarginRisk').textContent = fmtCurrency(marginAtRisk);
  document.getElementById('kpiHighRisk').textContent = highRiskCount.toLocaleString('en-US');
}

function updateDiscountTrend(pricingRows) {
  const byMonth = new Map();
  pricingRows.forEach(r => {
    const m = r.order_month;
    if (!byMonth.has(m)) byMonth.set(m, { num: 0, den: 0 });
    byMonth.get(m).num += (+r.discount_depth || 0) * (+r.line_list_revenue || 0);
    byMonth.get(m).den += (+r.line_list_revenue || 0);
  });
  const labels = [...byMonth.keys()].sort();
  const values = labels.map(m => byMonth.get(m).den > 0 ? (byMonth.get(m).num / byMonth.get(m).den) * 100 : 0);

  makeOrUpdateChart('discountTrendChart', {
    type: 'line',
    data: { labels, datasets: [{ label: 'Weighted discount (%)', data: values, borderColor: '#1d4ed8', backgroundColor: '#1d4ed822', tension: 0.25, fill: true }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { ticks: { callback: v => `${v.toFixed(0)}%` } } } }
  });
}

function updateDiscountBySegment(pricingRows) {
  const grouped = groupBy(pricingRows, r => r.segment, r => +r.discount_depth || 0);
  const labels = [...grouped.keys()].sort();
  const data = labels.map(k => grouped.get(k).reduce((a, b) => a + b, 0) / Math.max(1, grouped.get(k).length) * 100);

  makeOrUpdateChart('discountBySegmentChart', {
    type: 'bar',
    data: { labels, datasets: [{ label: 'Avg discount (%)', data, backgroundColor: '#e11d48cc' }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { callback: v => `${v.toFixed(0)}%` } } } }
  });
}

function updateInconsistencyByChannel(pricingRows) {
  const grouped = groupBy(pricingRows, r => r.sales_channel, r => +r.discount_depth || 0);
  const labels = [...grouped.keys()].sort();
  const avg = labels.map(k => grouped.get(k).reduce((a, b) => a + b, 0) / Math.max(1, grouped.get(k).length) * 100);

  makeOrUpdateChart('inconsistencyChart', {
    type: 'bar',
    data: { labels, datasets: [{ label: 'Avg discount (%)', data: avg, backgroundColor: '#f59e0bcc' }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true, ticks: { callback: v => `${v.toFixed(0)}%` } } } }
  });
}

function updateHighDiscountComposition(pricingRows) {
  let high = 0;
  let standard = 0;
  pricingRows.forEach(r => {
    if (+r.high_discount_flag === 1) high += (+r.line_revenue || 0);
    else standard += (+r.line_revenue || 0);
  });

  makeOrUpdateChart('highDiscountRevenueChart', {
    type: 'doughnut',
    data: { labels: ['Revenue >=20% discount', 'Revenue <20% discount'], datasets: [{ data: [high, standard], backgroundColor: ['#dc2626', '#60a5fa'] }] },
    options: { responsive: true, maintainAspectRatio: false, plugins: { legend: { position: 'bottom' }, tooltip: { callbacks: { label: (ctx) => `${ctx.label}: $${Math.round(ctx.parsed).toLocaleString('en-US')}` } } } }
  });
}

function updateTopGovernancePriorities(riskRows) {
  const grouped = groupBy(riskRows, r => r.recommended_action, r => +r.total_revenue || 0);
  const labels = [...grouped.keys()];
  const data = labels.map(k => grouped.get(k).reduce((a, b) => a + b, 0));
  const rows = labels.map((l, i) => ({ label: l, value: data[i] })).sort((a, b) => b.value - a.value);

  makeOrUpdateChart('prioritiesChart', {
    type: 'bar',
    data: { labels: rows.map(r => r.label), datasets: [{ label: 'Revenue impacted', data: rows.map(r => r.value), backgroundColor: '#0f766ecc' }] },
    options: { responsive: true, maintainAspectRatio: false, indexAxis: 'y', plugins: { legend: { display: false } }, scales: { x: { ticks: { callback: v => '$' + (v/1e6).toFixed(1) + 'M' } } } }
  });
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

function renderTable(riskRows) {
  const tbody = document.querySelector('#riskTable tbody');
  const sorted = sortRows(riskRows).slice(0, 120);
  tbody.innerHTML = sorted.map(r => `
    <tr>
      <td>${r.customer_id}</td>
      <td>${r.segment}</td>
      <td>${r.region}</td>
      <td>${fmtCurrency(+r.total_revenue || 0)}</td>
      <td>${fmtPct(+r.avg_discount_pct || 0)}</td>
      <td>${(+r.governance_priority_score || 0).toFixed(1)}</td>
      <td>${r.risk_tier}</td>
      <td>${r.recommended_action}</td>
    </tr>
  `).join('');
}

function updateAll() {
  const filters = getFilters();
  const pricingFiltered = applyPricingFilters(DATA.pricingRows, filters);
  const customerSet = new Set(pricingFiltered.map(r => r.customer_id));
  const riskFiltered = applyRiskFilters(DATA.riskRows, customerSet, filters);

  updateKpis(pricingFiltered, riskFiltered);
  updateDiscountTrend(pricingFiltered);
  updateDiscountBySegment(pricingFiltered);
  updateInconsistencyByChannel(pricingFiltered);
  updateHighDiscountComposition(pricingFiltered);
  updateTopGovernancePriorities(riskFiltered);
  renderTable(riskFiltered);
}

function init() {
  populateSelect(filterEls.segment, DATA.filterOptions.segment);
  populateSelect(filterEls.region, DATA.filterOptions.region);
  populateSelect(filterEls.category, DATA.filterOptions.category);
  populateSelect(filterEls.sales_channel, DATA.filterOptions.sales_channel);

  Object.values(filterEls).forEach(el => el.addEventListener('change', updateAll));
  document.querySelectorAll('#riskTable thead th').forEach(th => {
    th.addEventListener('click', () => {
      const key = th.getAttribute('data-key');
      if (tableState.key === key) tableState.dir = tableState.dir === 'asc' ? 'desc' : 'asc';
      else { tableState.key = key; tableState.dir = 'desc'; }
      updateAll();
    });
  });

  document.getElementById('metaLine').textContent = `Coverage: ${DATA.meta.coverage_start} to ${DATA.meta.coverage_end}`;
  document.getElementById('dataAsOf').textContent = DATA.meta.data_as_of;
  updateAll();
}

init();
</script>
</body>
</html>
"""

    html = html.replace("__DATA_JSON__", data_json).replace("__ALL_VALUE__", ALL_VALUE)

    dashboard_path = dashboard_dir / "pricing_discount_governance_dashboard.html"
    dashboard_path.write_text(html)
    (dashboard_dir / "dashboard_data_snapshot.json").write_text(json.dumps(payload))
    return dashboard_path
