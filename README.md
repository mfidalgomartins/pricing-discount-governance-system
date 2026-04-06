# Pricing Discipline & Discount Governance System

## Subtitle
A decision-focused pricing analytics system to separate nominal revenue growth from commercially healthy growth.

## First-Time Reader Guide
If this is your first time in the repository, this is what the project does in practical terms:
- **Business question:** is growth being achieved through pricing discipline or through discount dependency that weakens margin quality?
- **What was built:** a full analytics workflow from source data to validated KPIs, governance risk scoring, executive outputs, and a shareable dashboard.
- **Why it matters:** leadership can see where discounting is tactical vs structurally risky, and where policy intervention is worth the commercial tradeoff.
- **How it is engineered:** Python orchestration plus a warehouse-style SQL layer (`staging` -> `intermediate` -> `marts`) with reconciliation checks.

Quick orientation:
1. Read `Current Results Snapshot` for the headline answer.
2. Read `Validation Framework` to understand why the numbers are defensible.
3. Open `Outputs` and `Documentation` sections for deeper business and technical detail.

## Opening Summary
This project tests a common commercial failure mode: revenue rises while discounting quietly becomes the default way to close deals. The analysis quantifies whether performance reflects healthy price realization or dependency patterns that increase margin leakage and governance risk.

The deliverable is intentionally structured as business-facing analytics work, not a model demo: reproducible pipeline, explicit metric definitions, formal validation, interpretable scoring, and decision-ready reporting.

This repository now includes a warehouse-oriented SQL modeling layer (`staging` -> `intermediate` -> `marts`) to reflect real analytics engineering workflows.

## Business Problem Framing
Leadership teams often monitor top-line growth faster than pricing discipline. That creates blind spots:
- growth can be discount-led rather than value-led;
- margin pressure can concentrate in specific segments/channels/products;
- inconsistent rep behavior can bypass governance standards;
- discount dependency can become structurally embedded in customer behavior.

Core question:
Is the company growing through healthy pricing discipline, or relying on discounting patterns that erode margin and weaken commercial behavior?

## Analytical Grain and Data Model
- Transactional pricing grain: one row per order item (`order_item_id`).
- Behavioral governance grain: one row per customer profile (`customer_id`).
- Monitoring grains: monthly (`order_month`), segment, channel, product.

Core tables:
`customers`, `products`, `orders`, `order_items`, `sales_reps`

Processed analytical tables:
`order_item_enriched`, `order_item_pricing_metrics`, `customer_pricing_profile`, `segment_pricing_summary`, `segment_channel_diagnostics`, `customer_risk_scores`, `risk_tier_summary`, `main_driver_summary`

## Methodology
1. Ingest and validate source tables (schema, uniqueness, referential integrity).
2. Build a conformed order-item base table with commercial dimensions.
3. Engineer pricing and margin features at order-item and customer behavior levels.
4. Separate analysis layers:
- data profiling and data quality diagnostics
- descriptive and diagnostic pricing analysis
- interpretable risk scoring for governance prioritization
5. Publish outputs for executive reporting, operational review, and dashboard consumption.

## Warehouse Analytics Engineering Layer
- `sql/staging`: source-conformed models with typing and key hygiene.
- `sql/intermediate`: conformed order-item models with standardized pricing logic.
- `sql/marts`: stakeholder-facing analytical tables (customer/segment/channel/product/monthly).
- `scripts/run_sql_models.py`: executes SQL models into DuckDB and exports mart snapshots.
- `outputs/sql_validation_report.csv`: SQL-layer quality checks (PK uniqueness, reconciliation, bounds).

The SQL layer is intentionally kept interpretable and non-fragile; it mirrors the Python analytical logic without adding unnecessary orchestration complexity.

## Metric Definitions (Decision-Critical)
- Realized discount: `discount_depth = discount_pct` at order-item grain.
- Price realization: `line_revenue / line_list_revenue`.
- Weighted realized discount: `1 - (sum(line_revenue) / sum(line_list_revenue))`.
- High-discount revenue share: revenue share where discount >= 20%.
- Margin proxy %: `gross_margin_value / line_revenue` where `gross_margin_value = line_revenue - line_cost`.
- Repeat discount behavior: share of consecutive customer orders where both are high discount.

## Risk Scoring Logic (Interpretable, Not Black Box)
Scores are hybrid (0-100): relative peer ranking + absolute policy-breach intensity.
- `pricing_risk_score`: discount depth + price variability + high-discount order frequency (relative and threshold-anchored).
- `discount_dependency_score`: high-discount revenue share + repeat high-discount behavior + high-discount order frequency.
- `margin_erosion_score`: inverse margin proxy + discount depth + high-discount revenue share.
- `governance_priority_score`: weighted composite used for intervention prioritization.
- reliability control: low-order customers are shrunk toward a neutral score to reduce noisy false positives.

Risk tiers:
- `Critical` (>=80), `High` (65-79.99), `Medium` (45-64.99), `Low` (<45)

## Validation Framework
Validation is treated as first-class project scope, not a post-hoc check.

Implemented checks include:
- PK/FK integrity and join explosion prevention.
- Discount arithmetic consistency.
- Price consistency (`realized_unit_price <= list_price_at_sale`).
- Share/denominator sanity (`[0,1]` bounds).
- Weighted aggregation correctness (discount and margin consistency tests).
- Population coverage checks (explicit non-transacting customer exclusion visibility).

Primary validation artifacts (generated on run):
- `outputs/raw_validation_report.csv`
- `outputs/processed_validation_report.csv`
- `outputs/metric_contract_validation.csv`
- `outputs/formal_analysis_validation_checks.csv`
- `outputs/final_validation_issues.csv`
- `outputs/final_validation_readiness.csv`
- `outputs/final_validation_review.md`
- `outputs/final_validation_summary.json`
- `outputs/release/release_readiness.json`
- `outputs/release/release_gate_report.json`
- `outputs/sql_model_manifest.json`
- `outputs/sql_model_run_log.csv`
- `outputs/sql_validation_report.csv`

Release readiness is explicitly classified in the final validation layer as:
`technically_valid`, `analytically_acceptable`, `decision_support_only`, `screening_grade_only`, `not_committee_grade`, `publish_blocked`.

## Current Results Snapshot (Latest Run)
Latest run values are published to:
- `outputs/overall_pricing_health.csv`
- `outputs/yearly_pricing_health.csv`
- `outputs/formal_analysis_report.md`

Interpretation rule:
if weighted discount and high-discount revenue share remain structurally elevated, growth quality is discount-supported and should trigger governance action planning.
This is implemented in `formal_analysis` as a rule-based verdict engine (healthy / mixed / discount-reliant risk).

## Outputs
Versioned deliverables in the repository:
- `docs/reports/formal_analysis_report.md`
- `docs/reports/executive_summary.md`
- `docs/reports/data_profiling_report.md`
- `docs/reports/final_validation_review.md`
- `outputs/dashboard/pricing_discount_governance_dashboard.html`
- `outputs/dashboard/vendor/chart.umd.min.js`
- `outputs/visualizations/*.png`
- `notebooks/pricing_discount_governance_system.ipynb`

Generated run artifacts (not fully versioned):
- `outputs/*.csv`, `outputs/*.json`, `outputs/*.md`
- `data/processed/*.csv`, `data/processed/sql_marts/*.csv`
- `docs/reports/*.md`

These are regenerated by `python scripts/run_pipeline.py`.

## Documentation
- `docs/business_problem_and_metric_framework.md`
- `docs/data_model_and_grain.md`
- `docs/warehouse_analytics_layer.md`
- `docs/sql_query_patterns.md`
- `docs/validation_framework.md`
- `docs/governance_release_policy.md`
- `docs/reproducibility_and_artifact_policy.md`
- `docs/reports/*.md` (pipeline-generated analytical reports)

## Project Hygiene
- CI: `.github/workflows/ci.yml` runs preflight checks, compile checks, tests, and pipeline smoke-run on pushes and pull requests
- Release gate: `scripts/release_gate.py` enforces policy in `config/release_policy.json` before publish
- Metric contracts: `config/metric_contracts.json` defines governed KPI/table constraints
- Dependency policy: direct dependencies pinned in `requirements.txt`
- Preflight gate: `scripts/preflight_check.py` blocks oversized tracked files and missing core repo assets

## Business Value
This project is designed to support operating decisions, not only reporting:
- identify where discounting is tactical vs structurally dependency-driven;
- prioritize policy interventions where margin risk is concentrated;
- separate monitor-only cohorts from action-required cohorts;
- create a repeatable governance monitoring backbone for monthly business reviews.

## Limitations
- Data is synthetic (behaviorally designed), not observed company history.
- Margin is a modeled proxy from unit cost, not accounting gross margin.
- Rep outlier logic is threshold-based and should be calibrated with policy context.
- Dashboard remains a single-file artifact with embedded data; for very large populations, move to API-backed serving.

## Next Steps
1. Add intervention backtesting (before/after policy rule changes).
2. Add API-backed dashboard mode for very large datasets.
3. Add CI gating for validation/profiling output diffs.
4. Add budget/capacity constraints to action queue simulation (RevOps execution realism).

## Run
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python scripts/run_pipeline.py
# optional cleanup to keep repository tidy after runs
python scripts/cleanup_repository.py
# optional standalone SQL layer execution
python scripts/run_sql_models.py
python scripts/preflight_check.py
python scripts/release_gate.py
pytest -q
```
