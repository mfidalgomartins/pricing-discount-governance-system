# Pricing Discipline & Discount Governance

A decision-grade pricing governance system that shows where revenue is genuinely price-led and where it is structurally dependent on discounting. Built for commercial leaders who need early warning signals before margin quality erodes.

Live dashboard: https://mfidalgomartins.github.io/pricing-discount-governance-system/

## Why this exists
Discount-led growth can look healthy until it damages margin performance and commercial discipline. This project separates sustainable pricing from discount dependency, making exposure explicit across customer, segment, product, region, and channel views.

## What it delivers
It builds a governed pricing layer from transactional data, quantifies realized discount and price realization, and prioritizes governance risk with interpretable scoring and recommended actions. Outputs are reproducible, auditable, and built for decisions, not just reporting.

## Decisions it supports
- Which customers and segments need immediate pricing governance intervention.
- Which products and channels are structurally discount-dependent.
- Where margin-at-risk concentration is rising.
- Which governance actions should be prioritized first.

## Architecture
Ingestion -> Processing -> Feature engineering -> Risk scoring -> Validation -> Analysis outputs -> Executive dashboard.

## Repository map
- `src/` pipeline logic
- `scripts/` runnable entrypoints
- `config/` thresholds and metric contracts
- `docs/` methods and governance notes
- `outputs/` analysis artifacts and dashboard source build
- `tests/` regression checks

## Core outputs
- GitHub Pages entrypoint: `index.html`
- Final dashboard file: `outputs/dashboard/executive-pricing-discipline-command-center.html`
- Visualization pack: `outputs/visualizations/*.png`
- Validation evidence: `outputs/*validation*`

## Why this is stronger than a typical portfolio build
- Governance scoring is tied to operational actions, not vanity metrics.
- Metric contracts and validation checks reduce silent analytical drift.
- Business framing, outputs, and dashboard are aligned to pricing decisions.

## Run
```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
python scripts/run_pipeline.py
python scripts/publish_pages_dashboard.py
```

## Limitations
- Data is synthetic; production use requires real commercial inputs.
- Margin is a proxy, not audited accounting gross margin.
- Scoring supports prioritization, not autonomous pricing decisions.

Tools: Python, SQL, DuckDB, pandas, NumPy, Matplotlib, Seaborn, Chart.js, pytest.
