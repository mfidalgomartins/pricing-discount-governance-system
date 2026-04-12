# Formal Data Profiling Report

## Profiling Summary
### customer_pricing_profile
- Grain: 1 row per customer pricing behavior profile
- Likely primary key: customer_id
- Likely foreign keys: customer_id->customers.customer_id
- Row count: 1,173
- Column count: 17
- Date coverage: N/A
- Duplicates on primary key: 0
- Column classes:
  - metric: 13
  - dimension: 3
  - identifier: 1

### customer_risk_scores
- Grain: 1 row per customer scored for pricing governance risk
- Likely primary key: customer_id
- Likely foreign keys: customer_id->customer_pricing_profile.customer_id
- Row count: 1,173
- Column count: 20
- Date coverage: N/A
- Duplicates on primary key: 0
- Column classes:
  - metric: 12
  - dimension: 3
  - structural: 3
  - identifier: 1
  - boolean: 1

### customers
- Grain: 1 row per customer account
- Likely primary key: customer_id
- Likely foreign keys: N/A
- Row count: 1,200
- Column count: 5
- Date coverage: 2019-01-01 to 2022-12-30
- Duplicates on primary key: 0
- Column classes:
  - dimension: 3
  - identifier: 1
  - temporal: 1

### main_driver_summary
- Grain: 1 row per main risk driver
- Likely primary key: main_risk_driver
- Likely foreign keys: N/A
- Row count: 3
- Column count: 4
- Date coverage: N/A
- Duplicates on primary key: 0
- Column classes:
  - metric: 3
  - identifier: 1

### order_item_enriched
- Grain: 1 row per order line item with all dimensions attached
- Likely primary key: order_item_id
- Likely foreign keys: order_id->orders.order_id, customer_id->customers.customer_id, product_id->products.product_id, sales_rep_id->sales_reps.sales_rep_id
- Row count: 38,173
- Column count: 23
- Date coverage: 2023-01-01 to 2025-12-31
- Duplicates on primary key: 0
- Column classes:
  - dimension: 8
  - metric: 7
  - identifier: 5
  - structural: 2
  - temporal: 1

### order_item_pricing_metrics
- Grain: 1 row per order line item with pricing metrics
- Likely primary key: order_item_id
- Likely foreign keys: order_id->orders.order_id, customer_id->customers.customer_id, product_id->products.product_id, sales_rep_id->sales_reps.sales_rep_id
- Row count: 38,173
- Column count: 33
- Date coverage: 2023-01-01 to 2025-12-31
- Duplicates on primary key: 0
- Column classes:
  - metric: 14
  - dimension: 8
  - identifier: 5
  - structural: 3
  - boolean: 2
  - temporal: 1

### order_items
- Grain: 1 row per order line item
- Likely primary key: order_item_id
- Likely foreign keys: order_id->orders.order_id, product_id->products.product_id
- Row count: 38,173
- Column count: 7
- Date coverage: N/A
- Duplicates on primary key: 0
- Column classes:
  - metric: 4
  - identifier: 3

### orders
- Grain: 1 row per order header
- Likely primary key: order_id
- Likely foreign keys: customer_id->customers.customer_id, sales_rep_id->sales_reps.sales_rep_id
- Row count: 18,000
- Column count: 5
- Date coverage: 2023-01-01 to 2025-12-31
- Duplicates on primary key: 0
- Column classes:
  - identifier: 3
  - temporal: 1
  - dimension: 1

### products
- Grain: 1 row per product
- Likely primary key: product_id
- Likely foreign keys: N/A
- Row count: 28
- Column count: 5
- Date coverage: N/A
- Duplicates on primary key: 0
- Column classes:
  - dimension: 2
  - metric: 2
  - identifier: 1

### risk_tier_summary
- Grain: 1 row per risk_tier x recommended_action
- Likely primary key: risk_tier, recommended_action
- Likely foreign keys: N/A
- Row count: 3
- Column count: 5
- Date coverage: N/A
- Duplicates on primary key: 0
- Column classes:
  - metric: 3
  - identifier: 2

### sales_reps
- Grain: 1 row per sales rep
- Likely primary key: sales_rep_id
- Likely foreign keys: N/A
- Row count: 45
- Column count: 3
- Date coverage: N/A
- Duplicates on primary key: 0
- Column classes:
  - dimension: 2
  - identifier: 1

### segment_channel_diagnostics
- Grain: 1 row per segment x sales_channel
- Likely primary key: segment, sales_channel
- Likely foreign keys: N/A
- Row count: 16
- Column count: 7
- Date coverage: N/A
- Duplicates on primary key: 0
- Column classes:
  - metric: 5
  - identifier: 2

### segment_pricing_summary
- Grain: 1 row per customer segment
- Likely primary key: segment
- Likely foreign keys: N/A
- Row count: 4
- Column count: 9
- Date coverage: N/A
- Duplicates on primary key: 0
- Column classes:
  - metric: 8
  - identifier: 1

## Data Quality Issues (Severity Ranked)
- [Medium] customer_pricing_profile.customer_id: population_exclusion -> 27 customers (2.25%) have no transactions in period and are excluded

## Population Coverage
- Raw customers: 1,200
- Transacting customers: 1,173
- Profiled customers: 1,173
- Scored customers: 1,173
- Excluded non-transacting customers: 27 (2.25%)
- Transacting but not profiled: 0
- Profiled but not scored: 0

## Recommended Analytical Focus
### customer_pricing_profile
- Best dimensions for slicing: segment, region, company_size
- Best metrics for analysis: total_orders, total_order_items, total_revenue, avg_discount_pct, share_order_items_discounted, product_diversity, avg_margin_proxy_pct, realized_price_cv, share_orders_discounted, share_orders_high_discount
- Potential join keys: customer_id
- Likely hierarchies: region > segment
- Useful follow-up analyses: N/A
### customer_risk_scores
- Best dimensions for slicing: segment, region, company_size, risk_tier, main_risk_driver, recommended_action
- Best metrics for analysis: total_orders, total_revenue, avg_discount_pct, share_orders_discounted, share_orders_high_discount, revenue_high_discount_share, avg_margin_proxy_pct, pricing_risk_score, discount_dependency_score, margin_erosion_score
- Potential join keys: customer_id
- Likely hierarchies: region > segment
- Useful follow-up analyses: risk tier drift and intervention effectiveness
### customers
- Best dimensions for slicing: segment, region, company_size
- Best metrics for analysis: N/A
- Potential join keys: customer_id
- Likely hierarchies: region > segment
- Useful follow-up analyses: N/A
### main_driver_summary
- Best dimensions for slicing: N/A
- Best metrics for analysis: customers, total_revenue, avg_priority
- Potential join keys: main_risk_driver
- Likely hierarchies: N/A
- Useful follow-up analyses: N/A
### order_item_enriched
- Best dimensions for slicing: N/A
- Best metrics for analysis: quantity, list_price_at_sale, realized_unit_price, discount_pct, list_price, unit_cost, days_since_signup
- Potential join keys: order_item_id, order_id, customer_id, sales_rep_id, product_id
- Likely hierarchies: order_date > order_quarter > order_month
- Useful follow-up analyses: discount distribution stability and policy threshold adherence
### order_item_pricing_metrics
- Best dimensions for slicing: N/A
- Best metrics for analysis: quantity, list_price_at_sale, realized_unit_price, discount_pct, list_price, unit_cost, days_since_signup, realized_price, discount_depth, line_list_revenue
- Potential join keys: order_item_id, order_id, customer_id, sales_rep_id, product_id
- Likely hierarchies: order_date > order_quarter > order_month
- Useful follow-up analyses: discount distribution stability and policy threshold adherence
### order_items
- Best dimensions for slicing: N/A
- Best metrics for analysis: quantity, list_price_at_sale, realized_unit_price, discount_pct
- Potential join keys: order_item_id, order_id, product_id
- Likely hierarchies: N/A
- Useful follow-up analyses: discount distribution stability and policy threshold adherence
### orders
- Best dimensions for slicing: N/A
- Best metrics for analysis: N/A
- Potential join keys: order_id, customer_id, sales_rep_id
- Likely hierarchies: N/A
- Useful follow-up analyses: N/A
### products
- Best dimensions for slicing: category
- Best metrics for analysis: list_price, unit_cost
- Potential join keys: product_id
- Likely hierarchies: category > product_name
- Useful follow-up analyses: N/A
### risk_tier_summary
- Best dimensions for slicing: N/A
- Best metrics for analysis: customers, total_revenue, avg_governance_priority
- Potential join keys: risk_tier, recommended_action
- Likely hierarchies: N/A
- Useful follow-up analyses: N/A
### sales_reps
- Best dimensions for slicing: team, region
- Best metrics for analysis: N/A
- Potential join keys: sales_rep_id
- Likely hierarchies: N/A
- Useful follow-up analyses: N/A
### segment_channel_diagnostics
- Best dimensions for slicing: N/A
- Best metrics for analysis: revenue, avg_discount_pct, avg_margin_proxy_pct, high_discount_share, order_item_count
- Potential join keys: segment, sales_channel
- Likely hierarchies: N/A
- Useful follow-up analyses: N/A
### segment_pricing_summary
- Best dimensions for slicing: N/A
- Best metrics for analysis: total_revenue, avg_discount_pct, median_discount_pct, share_high_discount, avg_margin_proxy_pct, realized_price_variance, realized_price_std, margin_erosion_proxy
- Potential join keys: segment
- Likely hierarchies: N/A
- Useful follow-up analyses: N/A

## Data Model and Documentation Improvements
- Add a dedicated data dictionary table with business definitions, allowed ranges, and owners for each field.
- Introduce explicit data types and constraints (date parsing, numeric precision, enum lists) at ingestion boundaries.
- Version synthetic generation assumptions in docs so analytical changes are traceable over time.
- Add relationship tests (FK/PK) as automated checks in CI beyond local pytest execution.