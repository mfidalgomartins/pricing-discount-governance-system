# Executive Dashboard Guide

## Live access
https://mfidalgomartins.github.io/pricing-discount-governance-system/outputs/dashboard/pricing-discipline-command-center.html

## Main assets
- Source dashboard: `outputs/dashboard/pricing-discipline-command-center.html`
- GitHub Pages entrypoint: `index.html`

## Functional scope
- Filters: segment, region, product category, sales channel, start/end month
- KPI cards: net revenue, weighted discount, margin at risk, high-risk customers
- Charts: discount trend, segment comparison, region margin-at-risk, action mix
- Sortable risk table for top governance-priority customers

## Notes
- Data is embedded in the HTML payload at build time.
- KPI values use governed pre-aggregated metric rows.
- Chart interactivity uses local asset `outputs/dashboard/vendor/chart.umd.min.js` with CDN fallback.

## Limits
- Margin at risk is a governance proxy, not accounting gross margin.
- Data is synthetic.
