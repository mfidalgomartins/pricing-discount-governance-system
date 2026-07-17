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

## Required Raw Columns

These columns are the minimum operational contract for a successful pipeline run.

| Table | Required columns |
|---|---|
| `customers` | `customer_id`, `signup_date`, `segment`, `region`, `company_size` |
| `products` | `product_id`, `product_name`, `category`, `list_price`, `unit_cost` |
| `sales_reps` | `sales_rep_id`, `team`, `region` |
| `orders` | `order_id`, `customer_id`, `order_date`, `sales_channel`, `sales_rep_id` |
| `order_items` | `order_item_id`, `order_id`, `product_id`, `quantity`, `list_price_at_sale`, `realized_unit_price`, `discount_pct` |

Contract rules:
- Dates must parse as `YYYY-MM-DD` compatible values.
- Numeric price, cost, quantity, and discount fields must be numeric after CSV load.
- `products` must contain at least five products to cover all synthetic product categories.
- `orders.order_date` must be on or after the matching `customers.signup_date`.
- `discount_pct` must reconcile to `1 - realized_unit_price / list_price_at_sale` within validation tolerance.
- Real customer or contract data must not be committed to this repository.

## Processed Tables

| Table | Grain | Owner | Use |
|---|---|---|---|
| `order_item_enriched` | one row per order line | `src.processing.build_base_tables` | Joins order lines to customer, product, order, and sales rep dimensions with explicit many-to-one validation. |
| `order_item_pricing_metrics` | one row per order line | `src.features.pricing_features` | Adds line revenue, list revenue, discount depth, margin proxy, high-discount flags, and product/channel-normalized price-realization residuals. |
| `customer_pricing_profile` | one row per transacting customer | `src.features.pricing_features` | Aggregates discount dependency, margin proxy, realized-price variability, and repeat high-discount behavior. |
| `segment_pricing_summary` | one row per segment | `src.features.pricing_features` | Segment-level pricing quality, margin erosion proxy, and residual dispersion. |
| `customer_risk_scores` | one row per transacting customer | `src.scoring.risk_scoring` | Operational governance scoring and recommended action. This is a prioritization heuristic, not a causal or predictive model. |

## Key Metrics

| Metric | Unit | Meaning |
|---|---:|---|
| `line_revenue` | modeled USD | `quantity * realized_unit_price`. |
| `line_list_revenue` | modeled USD | `quantity * list_price_at_sale`. |
| `discount_depth` | percentage | Discount implied by realized price versus list price at sale. |
| `weighted_realized_discount` | percentage | Portfolio discount weighted by list revenue. |
| `weighted_discount_pct` | percentage | Customer discount weighted by line list revenue; the discount-depth input to customer risk scoring. |
| `price_realization` | percentage | Realized revenue divided by list revenue. |
| `margin_proxy_pct` | percentage | Order-line modeled margin proxy. At aggregate grains, margin is revenue-weighted as `sum(gross_margin_value) / sum(line_revenue)`. |
| `discounted_flag` | binary | `1` when discount is at or above `discounted_threshold` in `config/policy_thresholds.json` (default 5%). |
| `high_discount_flag` | binary | `1` when discount is at or above `high_discount_threshold` in `config/policy_thresholds.json` (default 20%). |
| `margin_at_risk_revenue` | modeled USD | Revenue on high-discount lines whose margin proxy is below `margin_at_risk_proxy_max` (default 35%). |
| `revenue_high_discount_share` | percentage | Share of customer revenue coming from high-discount lines. |
| `line_price_realization` | percentage | Realized unit price divided by list price at sale. |
| `price_realization_residual_pct` | percentage | Line price realization relative to the product/channel peer average, controlling for list-price level and product/channel mix. |
| `avg_abs_price_realization_residual_pct` | percentage | Customer mean absolute product/channel-normalized price-realization residual; the pricing-variance input to risk scoring. |
| `governance_priority_score` | 0-100 | Operational risk score combining weighted discount depth, dependency, normalized price variance, and margin signals. |

## Data Ownership and Rebuild Rules

- `data/raw/*.csv` and `data/processed/*` are runtime outputs regenerated by `scripts/run_pipeline.py`.
- SQL marts are exported to `data/processed/sql_marts/*.csv` and backed by `data/processed/pricing_governance.duckdb`.
- Published dashboard/report artifacts should be rebuilt only after raw, SQL, processed, metric-contract, final-review, and release-gate checks pass.
- The dashboard review queue targets 140 accounts for payload efficiency but always retains every Critical and High account, so high-risk counts are not truncated.
- If adapting to real data, keep the same table names and grains or update validation contracts before running analytics.
- Published monetary values use a modeled USD convention for readability; no currency conversion or FX analysis is implied.

## Validation Rules

The pipeline validates required columns, primary keys, foreign keys, not-null keys, bounds, row-count gates, no-silent-drop joins, revenue reconciliation, SQL-vs-pandas parity, and metric contracts before publishing conclusions.
