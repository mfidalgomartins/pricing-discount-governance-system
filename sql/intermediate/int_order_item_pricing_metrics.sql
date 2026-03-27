create or replace table int_order_item_pricing_metrics as
select
    e.order_item_id,
    e.order_id,
    e.customer_id,
    e.order_date,
    cast(date_trunc('month', e.order_date) as date) as order_month,
    concat(cast(extract(year from e.order_date) as varchar), '-Q', cast(extract(quarter from e.order_date) as varchar)) as order_quarter,
    e.sales_channel,
    e.sales_rep_id,
    e.product_id,
    e.quantity,
    e.list_price_at_sale,
    e.realized_unit_price,
    e.discount_pct,
    e.signup_date,
    e.segment,
    e.region,
    e.company_size,
    e.product_name,
    e.category,
    e.list_price,
    e.unit_cost,
    e.team,
    e.rep_region,
    e.days_since_signup,
    e.realized_unit_price as realized_price,
    e.discount_pct as discount_depth,
    case
        when e.discount_pct < 0.05 then '0-5%'
        when e.discount_pct < 0.10 then '5-10%'
        when e.discount_pct < 0.20 then '10-20%'
        when e.discount_pct < 0.30 then '20-30%'
        else '30%+'
    end as discount_bucket,
    e.quantity * e.list_price_at_sale as line_list_revenue,
    e.quantity * e.realized_unit_price as line_revenue,
    e.quantity * e.unit_cost as line_cost,
    (e.quantity * e.realized_unit_price) - (e.quantity * e.unit_cost) as gross_margin_value,
    case
        when (e.quantity * e.realized_unit_price) > 0
            then ((e.quantity * e.realized_unit_price) - (e.quantity * e.unit_cost)) / (e.quantity * e.realized_unit_price)
        else null
    end as margin_proxy_pct,
    case when e.discount_pct >= 0.20 then 1 else 0 end as high_discount_flag,
    case when e.discount_pct >= 0.05 then 1 else 0 end as discounted_flag
from int_order_item_enriched e;
