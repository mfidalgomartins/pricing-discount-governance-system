# Pricing Discipline & Discount Governance

Decision‑ready analysis of whether revenue growth is supported by pricing discipline or propped up by discount dependency that erodes margin quality.

## Business problem
Discount‑driven growth can look healthy until margin quality collapses. Leaders need to know which segments, products, and customers are structurally reliant on discounting and where governance action will pay back fastest.

## What the system does
- Builds a clean, auditable pricing dataset from raw transactional tables.
- Quantifies discount depth, price realization, and margin proxy exposure.
- Scores governance risk at the customer and segment level.
- Produces executive‑ready outputs and a dashboard for action.

## Decisions supported
- Which customers and segments to prioritize for pricing governance.
- Where discount dependency is structurally embedded.
- Which products and channels drive margin‑erosion risk.
- What level of discounting is still defensible by revenue quality.

## Project architecture
Ingestion → Processing → Features → Risk Scoring → Validation → Analysis → Dashboard.

## Repository structure
- `src/`: pipeline logic (ingestion, processing, features, scoring, validation, analysis)
- `scripts/`: runnable entrypoints
- `docs/`: methods, governance, and dashboard guide
- `outputs/`: dashboard, visuals, and analysis artifacts
- `tests/`: regression checks

## Core outputs
- Executive dashboard: `outputs/dashboard/pricing_discount_governance_dashboard.html`
- Visualization pack: `outputs/visualizations/*.png`
- Audit trail: `outputs/final_validation_*`, `outputs/metric_contract_validation.csv`

## Why this project is strong
- Decision‑oriented risk scoring tied to pricing governance actions.
- Explicit metric contracts and validation checks (not just charts).
- Outputs are reproducible and auditable, not hand‑curated.

## How to run
```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python scripts/run_pipeline.py
```

## Limitations
- Synthetic data; real conclusions require production inputs.
- Margin is a proxy, not audited gross margin.

## Tools
Tools: Python, pandas, NumPy, DuckDB, Matplotlib, Seaborn, Chart.js.
