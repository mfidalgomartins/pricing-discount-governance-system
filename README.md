# Pricing Discipline & Discount Governance

Analytics system for detecting discount leakage, margin erosion, and commercial risk. Uses a fully synthetic dataset and a reproducible Python + DuckDB pipeline.

[![CI](https://github.com/mfidalgomartins/pricing-discount-governance-system/actions/workflows/ci.yml/badge.svg)](https://github.com/mfidalgomartins/pricing-discount-governance-system/actions/workflows/ci.yml)
![Python](https://img.shields.io/badge/Python-3.12-blue)
![License](https://img.shields.io/badge/license-MIT-green)
![Data](https://img.shields.io/badge/data-100%25%20synthetic-orange)

**Live dashboard:** [Pricing Discipline Command Center](https://mfidalgomartins.github.io/pricing-discount-governance-system/)

> All data is synthetic and reproducible. No real customer, product, or transaction data is included. The governance score is a decision-support heuristic — it prioritizes review queues and does not claim causal attribution or validated prediction.

## Business Problem

Discount-led growth can look healthy while quietly reducing price realization and margin quality. This project builds a governed analytics layer that separates sustainable pricing performance from structural discount dependency across customers, segments, products, channels, regions, and sales reps.

## What It Delivers

- Reproducible synthetic commercial dataset.
- Python and DuckDB SQL pipeline from raw data to governed marts.
- Data quality checks for schema, PK/FK integrity, row-count gates, bounds, reconciliation, and no-silent-drop joins.
- Operational customer risk score with documented thresholds and caveats.
- Sensitivity analysis for discount and risk thresholds.
- Accessible, self-contained HTML dashboard generated under `outputs/dashboard/` and copied to `docs/` for GitHub Pages.
- Notebook and documentation for technical review.

## Dataset & Grain

| Layer | Main tables | Grain |
|---|---|---|
| Raw synthetic data | `customers`, `products`, `sales_reps`, `orders`, `order_items` | dimensions, order headers, and order lines |
| Processed pandas facts | `order_item_enriched`, `order_item_pricing_metrics` | one row per order item |
| Analytical aggregates | `customer_pricing_profile`, `segment_pricing_summary`, `customer_risk_scores` | customer, segment, and risk-score grains |
| SQL marts | `mart_customer_pricing_profile`, `mart_segment_pricing_summary`, `mart_overall_pricing_health` | warehouse-ready decision views |

See [docs/data_dictionary.md](docs/data_dictionary.md) for table definitions, keys, metrics, units, and synthetic-data caveats.

## Pipeline

```text
synthetic data
  -> raw validation
  -> DuckDB SQL warehouse
  -> pandas enrichment
  -> feature engineering
  -> risk scoring
  -> processed validation
  -> analysis and visualization
  -> dashboard publication
  -> release gate
```

The pipeline validates raw data before building SQL marts, validates pandas joins with explicit cardinality contracts, and uses data-derived dates so repeated runs with the same seed produce equivalent analytical outputs.

## Key Metrics

- `weighted_realized_discount`: list-revenue-weighted discount leakage.
- `price_realization`: realized revenue divided by list revenue.
- `high_discount_revenue_share`: revenue share from lines at or above the high-discount threshold.
- `margin_proxy_pct`: modeled margin proxy from synthetic unit cost.
- `realized_price_residual_pct`: product/channel-normalized price residual for pricing inconsistency diagnostics.
- `governance_priority_score`: operational score blending pricing risk, discount dependency, and margin erosion.

## Run Locally

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.lock
python scripts/run_pipeline.py
python scripts/preflight_check.py
pytest -q -p no:cacheprovider
```

For a faster smoke run:

```bash
python scripts/run_pipeline.py \
  --seed 11 \
  --customers 220 \
  --products 28 \
  --sales-reps 14 \
  --orders 2400 \
  --start-date 2024-01-01 \
  --end-date 2024-12-31
```

`--products` must be ≥ 5 (one per category). All thresholds are read from `config/policy_thresholds.json` and stay consistent with the sensitivity analysis.

## Outputs

- Local dashboard output: `outputs/dashboard/pricing-discipline-command-center.html`
- GitHub Pages dashboard copy: `docs/pricing-discipline-command-center.html`
- GitHub Pages entrypoint: `docs/index.html`
- Runtime outputs: regenerated locally under `outputs/`
- Processed tables and SQL marts: regenerated locally under `data/processed/`
- Notebook: `notebooks/pricing_discount_governance_system.ipynb`

Runtime outputs and processed marts are intentionally ignored because they are reproducible. The generated dashboard in `outputs/dashboard/` and the published copy in `docs/` are versioned.

## Tests & Quality Gates

```bash
python -m compileall -q src scripts tests
pytest -q -p no:cacheprovider
python scripts/preflight_check.py
```

Coverage focuses on raw validation order, pandas merge integrity, SQL warehouse reconciliation, deterministic as-of date, CLI validation, metric contracts, release gates, visualization outputs, and dashboard HTML/a11y contracts.

## Repository Map

```text
config/       policy thresholds, release policy, metric contracts
data/         synthetic raw inputs and generated processed data
docs/         GitHub Pages dashboard and project documentation
notebooks/    reproducible analytical notebook
scripts/      pipeline, dashboard, publishing, release and cleanup commands
sql/          DuckDB staging, intermediate, and mart models
src/          ingestion, processing, features, scoring, validation, analysis
tests/        pytest regression and quality checks
outputs/      local runtime reports and charts
```

## Methodological Limits

- Synthetic data supports methodology validation, not real-world commercial attribution.
- Margin is a modeled proxy, not audited accounting gross margin.
- Risk scores are operational heuristics and should not be treated as validated prediction models.
- Outlier and inconsistency signals flag review priorities, not misconduct.
- Realized-price variance can reflect product/channel mix; residual metrics are preferred for pricing inconsistency.

## License

MIT. See [LICENSE](LICENSE).
