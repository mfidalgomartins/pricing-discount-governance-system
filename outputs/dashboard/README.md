# Dashboard Assets

This directory stores the executive dashboard deliverable and its local JS dependency.

Primary assets:
- `pricing_discount_governance_dashboard.html`
- `vendor/chart.umd.min.js`

Notes:
- The dashboard is self-contained with embedded data payload.
- Customer table and action-priority chart use filter-consistent customer-level revenue aggregates.
- Chart.js is loaded from local `vendor/` first, with CDN fallback if local file is missing.
