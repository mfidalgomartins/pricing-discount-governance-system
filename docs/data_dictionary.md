# Data Dictionary

This project uses 100% synthetic commercial data. No real customer, product, sales rep, or transaction data is included.

## Source Tables

| Table | Grain | Primary key | Description |
|---|---|---|---|
| `customers` | one row per synthetic customer | `customer_id` | Customer dimension with segment, region, company size, and signup date. |
| `products` | one row per synthetic product | `product_id` | Product catalog with category, list price, and modeled unit cost. |
| `sales_reps` | one row per synthetic sales rep | `sales_rep_id` | Sales ownership dimension with team and region. |
| `orders` | one row per order header | `order_id` | Order header with customer, sales channel, sales rep, and order date. |
| `order_items` | one row per order line | `order_item_id` | Transaction line with product, quantity, list price at sale, realized unit price, and discount. |

## Processed Tables

| Table | Grain | Owner | Use |
|---|---|---|---|
| `order_item_enriched` | one row per order line | `src.processing.build_base_tables` | Joins order lines to customer, product, order, and sales rep dimensions with explicit many-to-one validation. |
| `order_item_pricing_metrics` | one row per order line | `src.features.pricing_features` | Adds line revenue, list revenue, discount depth, margin proxy, high-discount flags, and product/channel-normalized price residuals. |
| `customer_pricing_profile` | one row per transacting customer | `src.features.pricing_features` | Aggregates discount dependency, margin proxy, realized-price variability, and repeat high-discount behavior. |
| `segment_pricing_summary` | one row per segment | `src.features.pricing_features` | Segment-level pricing quality, margin erosion proxy, and residual dispersion. |
| `customer_risk_scores` | one row per transacting customer | `src.scoring.risk_scoring` | Operational governance scoring and recommended action. This is a prioritization heuristic, not a causal or predictive model. |

## Key Metrics

| Metric | Unit | Meaning |
|---|---:|---|
| `line_revenue` | currency | `quantity * realized_unit_price`. |
| `line_list_revenue` | currency | `quantity * list_price_at_sale`. |
| `discount_depth` | percentage | Discount implied by realized price versus list price at sale. |
| `weighted_realized_discount` | percentage | Portfolio discount weighted by list revenue. |
| `price_realization` | percentage | Realized revenue divided by list revenue. |
| `margin_proxy_pct` | percentage | Order-line modeled margin proxy. At aggregate grains, margin is revenue-weighted as `sum(gross_margin_value) / sum(line_revenue)`. |
| `high_discount_flag` | binary | `1` when discount is at or above `high_discount_threshold` in `config/policy_thresholds.json` (default 20%). |
| `revenue_high_discount_share` | percentage | Share of customer revenue coming from high-discount lines. |
| `realized_price_residual_pct` | percentage | Realized price deviation from the product/channel average, used to reduce product/channel mix bias. |
| `governance_priority_score` | 0-100 | Weighted operational risk score for prioritizing customer review. |

## Validation Rules

The pipeline validates required columns, primary keys, foreign keys, not-null keys, bounds, row-count gates, no-silent-drop joins, revenue reconciliation, SQL-vs-pandas parity, and metric contracts before publishing conclusions.
