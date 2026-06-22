# Validation Framework

## Validation Design Principles
- Catch structural failures before analysis artifacts are generated.
- Validate at both raw-source and analytical-model layers.
- Reconcile key financial totals to prevent silent join inflation.
- Keep checks auditable and easy to debug from exported reports.

## Raw Data Checks (`validate_raw_tables`)
- Required schema presence by table.
- Primary-key uniqueness by raw grain.
- Foreign-key integrity across core joins:
  - `orders.customer_id -> customers.customer_id`
  - `orders.sales_rep_id -> sales_reps.sales_rep_id`
  - `order_items.order_id -> orders.order_id`
  - `order_items.product_id -> products.product_id`
- Null controls for source tables.
- Pricing logic checks:
  - `0 <= discount_pct <= 0.7`
  - `realized_unit_price <= list_price_at_sale`
  - `quantity > 0`
  - recomputed discount absolute difference `<= 0.0001`
  - parseable customer/order dates and no orders before customer signup

## Processed Data Checks (`validate_processed_tables`)
- Required columns by analytical table.
- Grain uniqueness:
  - `order_item_pricing_metrics.order_item_id`
  - `customer_pricing_profile.customer_id`
  - `customer_risk_scores.customer_id`
- Bounds and logic checks:
  - score bounds `[0, 100]`
  - share metrics in `[0, 1]`
  - `discount_depth` bounds and `realized <= list`
  - weighted discount reconciliation (line-item weighted vs aggregate ratio)
  - line revenue, list revenue, cost, gross margin, margin percentage, and high-discount flag arithmetic
  - customer-level revenue-weighted margin reconciliation
- Taxonomy checks:
  - allowed `risk_tier` values
  - allowed `recommended_action` values
- Population consistency:
  - customer profile row count equals customer risk row count

## Runtime Artifacts
These files are generated under `outputs/` when the pipeline runs:
- `outputs/raw_validation_report.csv`
- `outputs/processed_validation_report.csv`
- `outputs/metric_contract_validation.csv`
- `outputs/formal_analysis_validation_checks.csv`
- `outputs/final_validation_issues.csv`
- `outputs/final_validation_readiness.csv`
- `outputs/final_validation_review.md`
- `outputs/final_validation_summary.json`

Operational rule: treat any `FAIL` status in these files as a blocker until reviewed. The pipeline raises an exception for blocker failures; do not reuse partially generated artifacts for publication.

## Final Review Layer (`run_final_validation_review`)
- Consolidates cross-layer spot checks into a single executive-ready review.
- Forces current-run consistency for:
  - join integrity and row-count sanity
  - FK consistency
  - discount arithmetic and pricing bounds
  - subtotal/total reconciliation
  - weighted metric correctness
  - period completeness
  - score variance sanity
  - run manifest row-count consistency vs current data
- Writes canonical outputs to `outputs/` to keep one governed report surface.
- Adds explicit release-readiness classification with governance gates:
  - `technically_valid`
  - `analytically_acceptable`
  - `decision_support_only`
  - `publish_blocked`

## Readiness Semantics
- `technically_valid`: structural and blocker checks pass (PK/FK, join-explosion, pricing arithmetic).
- `analytically_acceptable`: technical validity plus analytical consistency checks pass (denominators, totals, weighted logic).
- `decision_support_only`: analytically acceptable but constrained by decision caveats.
- `publish_blocked`: blocker checks fail; outputs should not be published or used for decisions.

## Release Gate

`scripts/release_gate.py` evaluates `outputs/final_validation_summary.json` and `outputs/metric_contract_validation.csv` against `config/release_policy.json`.

Current blocking rules:
- Required readiness flags must match policy.
- Failed checks must be `0`.
- Failed blocker checks must be `0`.
- Dashboard size must be below the configured maximum.
- Metric-contract failures must be `0`.

Outputs:
- `outputs/release/release_gate_report.json`
- `outputs/release/release_gate_report.md`

The full pipeline already runs this gate. Use the standalone script to re-check an existing run after reviewing generated outputs.

## Failure Triage

| Failure surface | First file to inspect | Common cause |
|---|---|---|
| Raw validation | `outputs/raw_validation_report.csv` | missing columns, duplicate keys, FK gaps, invalid dates, price arithmetic mismatch |
| SQL warehouse | `outputs/warehouse/sql_validation_report.csv` | no-silent-drop failure, mart grain duplication, revenue reconciliation drift |
| Processed validation | `outputs/processed_validation_report.csv` | score/share bounds, weighted metric mismatch, customer population mismatch |
| Metric contracts | `outputs/metric_contract_validation.csv` | changed metric name, unit, bound, nullability, or type |
| Release gate | `outputs/release/release_gate_report.md` | failed readiness flag, metric contract failure, oversized dashboard |
| Repository preflight | terminal output from `make preflight` | missing required artifact, stale dashboard copy, broken Markdown link, oversized/forbidden tracked file |
