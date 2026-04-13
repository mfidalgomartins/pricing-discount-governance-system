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
  - recomputed discount consistency tolerance

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
- Taxonomy checks:
  - allowed `risk_tier` values
  - allowed `recommended_action` values
- Population consistency:
  - customer profile row count equals customer risk row count

## Audit Artifacts
- `outputs/raw_validation_report.csv`
- `outputs/processed_validation_report.csv`
- `outputs/metric_contract_validation.csv`
- `outputs/formal_analysis_validation_checks.csv`
- `outputs/final_validation_issues.csv`
- `outputs/final_validation_readiness.csv`
- `outputs/final_validation_review.md`
- `outputs/final_validation_summary.json`

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
  - `screening_grade_only`
  - `not_committee_grade`
  - `publish_blocked`

## Readiness Semantics
- `technically_valid`: structural and blocker checks pass (PK/FK, join-explosion, pricing arithmetic).
- `analytically_acceptable`: technical validity plus analytical consistency checks pass (denominators, totals, weighted logic).
- `decision_support_only`: analytically acceptable but constrained by decision caveats.
- `screening_grade_only`: technically valid but analytical checks failed; usable for directional screening only.
- `not_committee_grade`: analytically acceptable but major evidence constraints remain (synthetic data and margin proxy).
- `publish_blocked`: blocker checks fail; outputs should not be published or used for decisions.
