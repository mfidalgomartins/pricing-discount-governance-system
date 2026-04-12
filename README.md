# Pricing Discipline & Discount Governance System

Revenue growth can hide weak pricing behavior. This project was built to expose that risk early, before discount habits become structural and margin deterioration is treated as a late surprise. It combines governed metrics, interpretable risk scoring, and executive-facing outputs to support pricing decisions with evidence.

## Why this matters
Many commercial teams can explain revenue growth but cannot explain its quality. If growth depends on repeated discounting, pricing power is weakening, sales behavior drifts by rep or channel, and margin pressure accumulates in silence. The goal here is simple: separate healthy growth from discount-led growth.

## What this system delivers
The pipeline starts with transactional data, builds warehouse-style analytical layers, and produces decision-ready outputs across customer, segment, product, channel, and rep views. It quantifies discount depth, price realization, margin proxy pressure, and governance risk, then translates those signals into a practical action queue.

The project is built for decisions, not just reporting. It helps answer where approval thresholds should be tightened, which products are being sold with weak pricing discipline, and where commercial behavior is inconsistent enough to require intervention.

## Architecture at a glance
- `src/ingestion` and `src/processing` build the base model and curated analytical tables
- `src/features` and `src/scoring` engineer behavior signals and governance scores
- `src/analysis` produces formal analysis outputs and dashboard-ready datasets
- `src/validation` enforces data quality, metric contracts, and release checks
- `sql/` contains staging, intermediate, and mart SQL models

## Repository layout
- `src/` core analytics and scoring logic
- `scripts/` runnable entrypoints
- `sql/` warehouse-oriented SQL layer
- `config/` metric contracts and governance thresholds
- `docs/` methods, model, validation, dashboard notes
- `outputs/` dashboard, visualizations, analysis, profiling, validation, release artifacts
- `tests/` regression and governance tests

## Core deliverables
- Executive dashboard: `outputs/dashboard/pricing_discount_governance_dashboard.html`
- Visualization pack: `outputs/visualizations/`
- Formal analysis tables and summaries: `outputs/analysis/`
- Profiling, validation, and release evidence: `outputs/profiling/`, `outputs/release/`, `outputs/*validation*`

## Why this project stands out
This is not a chart-first portfolio exercise. It uses explicit analytical grains, governed KPI definitions, release-gate checks, and traceable outputs designed for commercial leadership and finance conversations. The emphasis is on decision quality, reproducibility, and defensible logic.

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/run_pipeline.py
python scripts/build_visualization_pack.py
python scripts/build_dashboard.py
python scripts/preflight_check.py
pytest -q
```

## Limits to keep in mind
The data is synthetic, so behavior realism is strong but still simulated. Margin is a proxy based on unit cost, not full accounting margin. Risk scores are decision-support signals for prioritization, not autonomous pricing rules.

Tools: Python, SQL, DuckDB, pandas, NumPy, Matplotlib, Seaborn, Plotly, Chart.js, pytest.
