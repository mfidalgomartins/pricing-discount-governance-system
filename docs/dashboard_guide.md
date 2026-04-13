# Executive Dashboard Guide

## Live access
https://mfidalgomartins.github.io/pricing-discount-governance-system/

## Main assets
- Final dashboard source artifact: `outputs/dashboard/pricing-discipline-command-center.html`
- GitHub Pages published artifact: `docs/pricing-discipline-command-center.html`
- GitHub Pages entrypoint: `docs/index.html`

## Functional scope
- Filters: segment, region, product category, sales channel, start/end month
- KPI cards: net revenue, weighted discount, margin at risk, high-risk customers
- Charts: discount trend, segment comparison, region margin-at-risk, action mix
- Sortable risk table for top governance-priority customers

## Notes
- Data is embedded in the HTML payload at build time.
- KPI values use governed pre-aggregated metric rows.
- Chart interactivity uses local asset `docs/vendor/chart.umd.min.js` with CDN fallback.
- The dashboard is maintained in a single canonical location under `outputs/dashboard`.

## Limits
- Margin at risk is a governance proxy, not accounting gross margin.
- Data is synthetic.
