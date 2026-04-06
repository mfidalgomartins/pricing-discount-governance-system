# Executive Dashboard Guide

## Purpose
Provide a leadership-ready view of pricing health, discount dependency, margin-at-risk exposure, and governance priorities.

## Main Asset
- `outputs/dashboard/pricing_discount_governance_dashboard.html`

## Included Sections
- Executive title/subtitle and coverage metadata.
- Filter controls: segment, region, product category, sales channel.
- KPI cards:
  - net revenue
  - weighted discount
  - margin at risk
  - high-risk customer count
- Charts:
  - discount trend over time
  - weighted discount by segment
  - margin-at-risk by region
  - revenue exposure by recommended action
- Sortable detail table of highest-risk customers.

## Data Used
- `data/processed/order_item_pricing_metrics.csv` (aggregated for dashboard payload)
- `data/processed/customer_risk_scores.csv`

## Notes
- Data is embedded directly into the HTML at build time.
- Dashboard payload uses governed pre-aggregated pricing slices plus customer-level filtered revenue aggregates.
- KPI cards consume governed precomputed metric rows (`kpiRows`) rather than on-the-fly KPI math in the browser.
- Risk table and action-priority chart are filter-consistent: customer revenue and discount values reflect the active filter context.
- Chart interactivity uses a bundled local asset (`outputs/dashboard/vendor/chart.umd.min.js`) with CDN fallback.
- Dashboard is responsive and presentation-ready.

## Limitations
- Dashboard is offline-capable if the local `vendor/chart.umd.min.js` file is kept with the HTML.
- Margin at risk is a governance proxy, not accounting gross margin.
- The underlying dataset is synthetic.
- For production use at scale, move to API-backed data and incremental refresh.
