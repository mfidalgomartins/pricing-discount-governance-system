# Reproducibility and Artifact Policy

## Reproducibility Standard
- Python dependencies are pinned in `requirements.txt`.
- CI runs compile checks, unit tests, and a smoke pipeline execution.
- Main pipeline entrypoint: `scripts/run_pipeline.py`.
- Visualization backend is forced to non-interactive `Agg` to prevent OS-specific GUI backend failures in CLI/CI runs.

## Artifact Policy
Versioned artifacts (kept in git):
- Core source code in `src/`, `scripts/`, and `sql/`
- Narrative docs in `docs/`
- Dashboard deliverable in `dashboard/pricing_discount_governance_dashboard.html`
- Dashboard local JS dependency in `dashboard/vendor/chart.umd.min.js`
- Visualization images in `outputs/visualizations/`

Generated local artifacts (not fully versioned):
- `outputs/*.csv`, `outputs/*.json`, `outputs/*.md`
- `data/raw/*.csv`
- `data/processed/*.csv`, `data/processed/*.duckdb`
- `data/processed/sql_marts/*.csv`
- `docs/reports/*.md`

Pipeline-generated governance review artifacts:
- `outputs/final_validation_review.md`
- `outputs/final_validation_summary.json`
- `outputs/final_validation_issues.csv`
- `outputs/metric_contract_validation.csv`
- `outputs/release/release_readiness.json`
- `outputs/release/release_gate_report.json`

Rationale:
- Keep repository lightweight and reviewable.
- Keep reproducibility through deterministic pipeline + pinned dependencies.
- Avoid committing bulky tabular snapshots that are regenerated each run.

## Regeneration Commands
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/run_pipeline.py
python scripts/cleanup_repository.py
```

## Validation Gates
- `pytest -q`
- `python -m compileall -q src scripts tests`
- `python scripts/preflight_check.py`
- `python scripts/release_gate.py`
- CI smoke run on pull requests and pushes to `main`

`release_gate.py` enforces policy defined in `configs/release_policy.json`.  
By default it allows `not committee-grade` runs in portfolio synthetic mode while still requiring technical and analytical validity.
