# Warehouse-Oriented Analytics Layer

## Why This Layer Exists
The Python pipeline remains the main orchestration path, but a warehouse-style SQL layer has been added to make transformation logic auditable in SQL and closer to production analytics engineering patterns.

This layer improves realism by separating:
- source cleanup (`staging`)
- reusable joins and business logic (`intermediate`)
- decision-facing aggregates (`marts`)

## Folder Structure
- `sql/staging`: source-conformed views with typing and null-key guards.
- `sql/intermediate`: conformed transactional models at stable analytical grain.
- `sql/marts`: stakeholder-facing metric tables with explicit business semantics.

## Execution Path
- Runner: `scripts/run_sql_models.py`
- Core implementation: `src/processing/sql_warehouse.py`
- Warehouse file: `data/processed/pricing_governance.duckdb`
- Mart exports: `data/processed/sql_marts/*.csv`
- SQL run logs: `outputs/warehouse/sql_model_run_log.csv`, `outputs/warehouse/sql_validation_report.csv`, `outputs/warehouse/sql_model_manifest.json`

## Layer Details

### Staging Layer
Purpose: normalize raw fields and enforce minimal data contracts before joins.

Models:
- `stg_customers` (grain: customer)
- `stg_products` (grain: product)
- `stg_orders` (grain: order)
- `stg_order_items` (grain: order item)
- `stg_sales_reps` (grain: sales rep)

Key behavior:
- Explicit type casting for dates and numeric fields.
- Null-key row exclusion where primary identifiers are missing.

### Intermediate Layer
Purpose: centralize heavy join logic and pricing metric derivations once.

Models:
- `int_order_item_enriched` (grain: order item)
- `int_order_item_pricing_metrics` (grain: order item)

Key behavior:
- Join contract: `order_items -> orders -> customers + products + sales_reps`.
- Derived fields: `line_revenue`, `line_list_revenue`, `gross_margin_value`, `margin_proxy_pct`, `discount_bucket`, high-discount flags.
- Time dimensions: `order_month`, `order_quarter`.

### Mart Layer
Purpose: serve business analytics and governance decisions with stable grains.

Models:
- `mart_customer_pricing_profile` (grain: customer)
- `mart_segment_pricing_summary` (grain: segment)
- `mart_segment_channel_diagnostics` (grain: segment x channel)
- `mart_product_pricing_summary` (grain: product)
- `mart_monthly_pricing_health` (grain: month)
- `mart_overall_pricing_health` (grain: snapshot row)

## Metric Definitions (Warehouse Precision)
- `weighted_realized_discount = 1 - sum(line_revenue) / sum(line_list_revenue)`
- `price_realization = sum(line_revenue) / sum(line_list_revenue)`
- `margin_proxy_pct = sum(gross_margin_value) / sum(line_revenue)`
- `share_orders_high_discount = avg(high_discount_order)` at customer order grain
- `revenue_high_discount_share = revenue_high_discount / total_revenue`
- `margin_erosion_proxy = (1 - avg_margin_proxy_pct) * share_high_discount * 100`

All percentage-style share metrics are bounded to `[0,1]` by validation checks.

## SQL Validation Controls
Implemented in `src/processing/sql_warehouse.py`:
- row-count positive checks for all marts
- primary-key uniqueness checks by mart grain
- revenue reconciliation (`intermediate` vs `segment` vs `monthly` marts)
- share-bounds checks for customer mart
- pricing consistency checks (`discount_depth` bounds, `realized <= list`)

## Reusable Query Patterns
Common stakeholder questions can be answered directly from marts:
- trend governance KPIs by month (`mart_monthly_pricing_health`)
- segment/channel policy pressure (`mart_segment_channel_diagnostics`)
- customer intervention queue (`mart_customer_pricing_profile`)
- product pricing dependence ranking (`mart_product_pricing_summary`)

See `docs/sql_query_patterns.md` for concrete query templates.

## Productionization Guidance
A real team could productionize this workflow by:
1. Moving SQL models into dbt or a warehouse-native scheduler.
2. Registering model contracts (types, tests, ownership) in CI.
3. Incrementalizing `int_order_item_pricing_metrics` by order date partition.
4. Publishing marts to BI semantic layer with governed metric names.
5. Versioning threshold policies (high-discount, risk tiers) as controlled config.

## Performance Notes
- Join and metric derivation are centralized in intermediate tables to avoid repeated scans.
- Mart aggregations consume intermediate data rather than rejoining raw tables.
- Revenue reconciliation checks guard against accidental double counting from join cardinality drift.
