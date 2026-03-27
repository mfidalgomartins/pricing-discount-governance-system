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

## SQL Warehouse Checks (`run_sql_warehouse_models`)
- Positive row counts for all marts.
- Mart primary-key uniqueness by defined grain.
- Revenue reconciliation between intermediate and mart aggregations.
- Customer share bounds in marts.
- Pricing consistency in intermediate model.

## Audit Artifacts
- `outputs/raw_validation_report.csv`
- `outputs/processed_validation_report.csv`
- `outputs/sql_validation_report.csv`
- `outputs/formal_analysis_validation_checks.csv`
- `outputs/final_validation_review.md`
- `outputs/final_validation_summary.json`
