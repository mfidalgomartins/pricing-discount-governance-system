# Pricing Discipline & Discount Governance

A decision‑grade pricing governance system that surfaces where revenue is genuinely price‑led and where it is structurally dependent on discounting. Built to support commercial leaders who need early warning signals before margin quality collapses.

## Why this exists
Discount‑driven growth often looks healthy right up to the moment it damages margin performance and commercial credibility. This project separates sustainable pricing from dependency, and makes the trade‑offs explicit at customer, segment, product, and channel level.

## What it does
It builds a clean transactional pricing layer, quantifies realized discount and price realization, and produces governance risk scores that rank where intervention will have the highest business impact. The outputs are reproducible, auditable, and designed to support real decisions rather than just describing trends.

## Decisions it supports
- Which customers and segments require immediate pricing governance.
- Which products and channels carry structural discount dependency.
- Where margin‑erosion exposure is concentrated and rising.
- What discount intensity is still defensible by revenue quality.

## Architecture (at a glance)
Ingestion → Processing → Feature engineering → Risk scoring → Validation → Analysis → Executive dashboard.

## Repository map
- `src/` pipeline logic
- `scripts/` runnable entrypoints
- `docs/` methods and governance notes
- `outputs/` dashboard, visuals, and audit trail
- `tests/` regression checks

## Core outputs
- Executive dashboard: `outputs/dashboard/pricing_discount_governance_dashboard.html`
- Visualization pack: `outputs/visualizations/*.png`
- Audit trail: `outputs/final_validation_*`, `outputs/metric_contract_validation.csv`

## Why this is above a typical portfolio build
- Governance scoring tied to decision actionability, not vanity metrics.
- Metric contracts and validation layers to prevent silent drift.
- Outputs are reproducible and auditable, not hand‑assembled.

## Run
```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python scripts/run_pipeline.py
```

## Limitations
- Synthetic data; production use requires real inputs.
- Margin is a proxy, not audited gross margin.

Tools: Python, pandas, NumPy, DuckDB, Matplotlib, Seaborn, Chart.js.
