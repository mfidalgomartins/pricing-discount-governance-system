# Reusable SQL Query Patterns

The warehouse layer exposes stable marts for repeated business questions. These patterns assume execution against `data/processed/pricing_governance.duckdb`.

## 1) Monthly Governance Health Trend
```sql
select
    order_month,
    revenue,
    weighted_discount_pct,
    margin_proxy_pct,
    high_discount_share
from mart_monthly_pricing_health
order by order_month;
```
Why: supports recurring pricing-governance KPI review in leadership cadence.

## 2) Segment and Channel Pressure Map
```sql
select
    segment,
    sales_channel,
    revenue,
    avg_discount_pct,
    avg_margin_proxy_pct,
    high_discount_share
from mart_segment_channel_diagnostics
order by segment, avg_discount_pct desc;
```
Why: isolates where discounting pressure and margin risk are structurally concentrated.

## 3) Customer Intervention Queue
```sql
select
    customer_id,
    segment,
    region,
    total_revenue,
    avg_discount_pct,
    revenue_high_discount_share,
    share_orders_high_discount,
    repeat_discount_behavior
from mart_customer_pricing_profile
where revenue_high_discount_share >= 0.40
order by total_revenue desc;
```
Why: prioritizes customers with commercially meaningful discount dependency.

## 4) Product Pricing Dependence Ranking
```sql
select
    product_id,
    product_name,
    category,
    revenue,
    avg_discount_pct,
    high_discount_share,
    price_realization
from mart_product_pricing_summary
order by high_discount_share desc, revenue desc;
```
Why: highlights products that may need pricing architecture review.

## 5) Reconciliation Control Pattern
```sql
with base as (
    select sum(line_revenue) as base_revenue
    from int_order_item_pricing_metrics
),
segment as (
    select sum(total_revenue) as segment_revenue
    from mart_segment_pricing_summary
),
monthly as (
    select sum(revenue) as monthly_revenue
    from mart_monthly_pricing_health
)
select
    base.base_revenue,
    segment.segment_revenue,
    monthly.monthly_revenue,
    base.base_revenue - segment.segment_revenue as base_minus_segment,
    base.base_revenue - monthly.monthly_revenue as base_minus_monthly
from base
cross join segment
cross join monthly;
```
Why: fast subtotal/total reconciliation check for preventing silent join drift.
