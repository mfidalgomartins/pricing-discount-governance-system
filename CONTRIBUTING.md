# Contributing

This is a portfolio project, not an open-source product. Forks and personal
adaptations are welcome; please do not expect upstream feature requests to be
prioritised.

## Setting up

```bash
make install   # creates .venv and installs requirements.lock
make test      # runs the full pytest suite with coverage
make run-smoke # ~30 s end-to-end pipeline at reduced scale
```

## Before opening a PR

```bash
make lint      # python -m compileall on src/ scripts/ tests/
make test      # pytest must stay green
make preflight # repository file-contract check
```

If you change any threshold, score weight, or metric definition,
update `config/policy_thresholds.json` rather than hardcoding values
in source. The whole pipeline is built around a single source of truth
for policy parameters.

If you change the pandas pipeline (`src/processing/`, `src/features/`,
`src/scoring/`), confirm that:

1. `make run-smoke` still produces `Release gate passed: True`
2. `outputs/processed_validation_report.csv` still has zero failures
3. `outputs/metric_contract_validation.csv` still has zero failures

If you change the dashboard (`src/analysis/dashboard_builder.py`), the
test suite enforces accessibility contracts — keyboard-sortable tables,
`aria-sort`, alt-text for canvases, and a `<noscript>` fallback. Do not
weaken these.

## Data policy

All data in this repo is synthetic and generated deterministically from
`src/ingestion/synthetic_data.py`. **Never commit real customer, product,
or transaction data to a fork that is published.** The synthetic-only
posture is what makes the dashboard publishable.
