# Executive Dashboard Guide

## Purpose
Provide a leadership-ready view of pricing health, discount dependency, margin-at-risk exposure, and governance priorities.

## Main Asset
- `dashboard/pricing_discount_governance_dashboard.html`

## Included Sections
- Executive title/subtitle and coverage metadata.
- Filter controls: segment, region, product category, sales channel.
- KPI cards:
  - net revenue
  - average discount
  - margin at risk
  - high-risk customer count
- Charts:
  - discount trend over time
  - discount by segment
  - pricing inconsistency by channel
  - revenue under high discount
  - top governance priorities
- Sortable detail table of highest-risk customers.

## Data Used
- `data/processed/order_item_pricing_metrics.csv`
- `data/processed/customer_risk_scores.csv`

## Notes
- Data is embedded directly into the HTML at build time.
- Chart interactivity uses Chart.js via CDN.
- Dashboard is responsive and presentation-ready.
- Current self-contained HTML payload is larger than ideal due embedded row-level data.

## Limitations
- Offline rendering requires Chart.js availability (CDN dependency).
- Margin at risk is a governance proxy, not accounting gross margin.
- The underlying dataset is synthetic.
- For production use, move to pre-aggregated API-backed data and bundle JS locally for true offline portability.
