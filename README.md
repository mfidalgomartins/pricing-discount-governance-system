# Pricing Discipline & Discount Governance System

A decision-support analytics system to detect when revenue growth is being bought through discounting that weakens pricing discipline and margin quality.

## Business problem
Revenue can grow while commercial quality deteriorates. When discounting becomes structural, margin erosion is delayed in reporting and hard to reverse. The practical question is where growth is healthy and where pricing governance is failing.

## What the system does
- Builds a full pipeline from synthetic transactional data to governed analytical outputs.
- Produces pricing, discount dependency, and margin erosion metrics at customer, segment, product, channel, and rep levels.
- Scores governance risk with interpretable components and clear action mapping.
- Publishes executive outputs: one HTML dashboard, chart pack, and auditable analysis tables.

## Decisions supported
- Which customers and segments need tighter discount approval thresholds.
- Which products are discount-dependent and require pricing or packaging review.
- Which channels or reps show inconsistent pricing behavior.
- Where to prioritize governance actions for highest margin protection impact.

## Project architecture
- `ingestion`: synthetic source tables and loading.
- `processing`: base joins, warehouse-style models, curated analytical tables.
- `features`: pricing behavior and dependency features.
- `scoring`: risk components and governance priority scoring.
- `analysis`: formal reporting outputs and dashboard data feed.
- `validation`: data quality, metric contracts, and release gate checks.

## Repository structure
- `src/` core analytics code
- `scripts/` runnable entrypoints
- `sql/` staging, intermediate, mart SQL models
- `config/` metric contracts and governance thresholds
- `docs/` methods, data model, validation, and dashboard notes
- `outputs/` dashboard, charts, analysis, profiling, validation, release artifacts
- `tests/` pipeline, metric, dashboard, and release tests

## Core outputs
- Executive dashboard: `outputs/dashboard/pricing_discount_governance_dashboard.html`
- Visualization pack: `outputs/visualizations/*.png`
- Formal analysis outputs: `outputs/analysis/*`
- Profiling and validation evidence: `outputs/profiling/*`, `outputs/*validation*`, `outputs/release/*`

## Why this project is strong
- Business-first framing with explicit governance decisions, not metric dumping.
- Clear analytical grains and metric contracts to avoid ambiguous KPI logic.
- Validation and release discipline to reduce silent analytical failure.
- End-to-end reproducibility with auditable outputs suitable for stakeholder review.

## How to run
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

## Limitations
- Data is synthetic; signal realism is strong but not equivalent to production noise.
- Margin is a proxy (`unit_cost` based), not full financial accounting margin.
- Scoring supports prioritization and screening, not autonomous pricing decisions.

## Tools
Tools: Python, SQL, DuckDB, pandas, NumPy, Matplotlib, Seaborn, Plotly, Chart.js, pytest.
