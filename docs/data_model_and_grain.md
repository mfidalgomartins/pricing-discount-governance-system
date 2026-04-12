# Data Model, Grains, and Join Contracts

## Business-Critical Grains
- **Order item grain**: one row per line item (`order_item_id`).
- **Customer grain**: one row per customer (`customer_id`) for behavior/risk profiling.
- **Segment grain**: one row per segment for governance monitoring.
- **Segment x Channel grain**: one row per segment-channel pair for policy diagnostics.
- **Monthly grain**: one row per month for trend monitoring.

## Raw Sources
- `customers` (PK: `customer_id`)
- `products` (PK: `product_id`)
- `orders` (PK: `order_id`, FK: `customer_id`, `sales_rep_id`)
- `order_items` (PK: `order_item_id`, FK: `order_id`, `product_id`)
- `sales_reps` (PK: `sales_rep_id`)

## Analytical Tables (Processed)
- `order_item_enriched` (order item grain)
- `order_item_pricing_metrics` (order item grain)
- `customer_pricing_profile` (customer grain)
- `segment_pricing_summary` (segment grain)
- `segment_channel_diagnostics` (segment x channel grain)
- `customer_risk_scores` (customer grain)
- `risk_tier_summary` (risk tier x action grain)
- `main_driver_summary` (risk-driver grain)

## Join Contract and Cardinality
Canonical join path:
`order_items (N) -> orders (1) -> customers (1)`
`order_items (N) -> products (1)`
`orders (N) -> sales_reps (1)`

Cardinality expectation:
- Every `order_item` maps to exactly one `order` and one `product`.
- Every `order` maps to exactly one `customer` and one `sales_rep`.
- Intermediate joins preserve order-item grain (no row multiplication).

## Why These Tables Exist
- `int_order_item_pricing_metrics`: single source of truth for discount and margin-derived columns.
- `mart_customer_pricing_profile`: customer-level behavior needed for governance actioning.
- `mart_segment_pricing_summary`: segment-level governance KPI reporting.
- `mart_segment_channel_diagnostics`: where pricing policy pressure is operationally concentrated.
- `mart_monthly_pricing_health`: recurring trend KPI backbone.

## Grain-Aware Metric Rules
- Never average percentage metrics across pre-aggregated tables without weighting.
- Weighted discount must reconcile to revenue/list-revenue ratio.
- Shares must retain explicit denominator context (`orders`, `order_items`, or `revenue`).

## Validation Dependencies
- PK uniqueness is required at each mart grain.
- Revenue subtotals (segment/monthly) must reconcile to intermediate totals.
- Customer-profile and risk-score populations must stay aligned for transacting customers.
