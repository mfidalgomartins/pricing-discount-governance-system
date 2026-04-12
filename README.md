# Pricing Discipline & Discount Governance

Decision-focused analytics project to test whether growth quality is supported by pricing discipline or by discount dependency that weakens margin outcomes.

## What this project answers
Commercial leaders often see revenue growth before they see pricing quality deterioration. This project quantifies:
- how much revenue is discount-supported,
- where discounting is structurally embedded (customers, segments, products, channels),
- where margin proxy erosion is concentrated,
- which accounts should be prioritized for governance action.

## What is built
- End-to-end Python pipeline from raw tables to governed outputs.
- Explicit, auditable metrics and validation.
- Interpretable risk scoring (`pricing`, `dependency`, `margin`, `governance priority`).
- Validation checks designed for portfolio credibility (not production certification).
- One executive HTML dashboard (`outputs/dashboard/pricing_discount_governance_dashboard.html`).

## Repository layout
- `src/`: ingestion, transformations, analysis, scoring, validation.
- `scripts/`: runnable entrypoints.
- `config/`: metric contracts and dashboard posture thresholds.
- `docs/`: core methods and governance docs.
- `outputs/`: portfolio deliverables (`dashboard/`, `visualizations/`).
- `tests/`: regression and governance checks.

## Core analytical tables
- `order_item_pricing_metrics` (order-item grain)
- `customer_pricing_profile` (customer grain)
- `segment_pricing_summary` (segment grain)
- `customer_risk_scores` (customer governance grain)

## Key metric definitions
- `weighted_realized_discount = 1 - sum(line_revenue) / sum(line_list_revenue)`
- `price_realization = sum(line_revenue) / sum(line_list_revenue)`
- `high_discount_revenue_share`: revenue share from lines with discount >= 20%
- `margin_proxy_pct = (line_revenue - line_cost) / line_revenue`

## Governance scoring approach
Each score mixes peer-relative ranking with absolute policy-breach intensity:
- `pricing_risk_score`
- `discount_dependency_score`
- `margin_erosion_score`
- `governance_priority_score` (composite)

Low-volume customers are reliability-shrunk to reduce false positives.

## Validation discipline
The project enforces hard checks for:
- PK/FK integrity and join safety
- discount arithmetic and pricing bounds
- denominator correctness and bounded shares
- metric contract compliance


## Main deliverables
- Dashboard: `outputs/dashboard/pricing_discount_governance_dashboard.html`
- Charts: `outputs/visualizations/*.png`

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/run_pipeline.py
python scripts/preflight_check.py
pytest -q
```

## Documentation
- `docs/project_context_and_metrics.md`
- `docs/data_model_and_grain.md`
- `docs/validation_framework.md`
- `docs/release_and_reproducibility.md`
- `docs/dashboard_guide.md`
