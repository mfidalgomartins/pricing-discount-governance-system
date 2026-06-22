create or replace table mart_product_pricing_summary as
with product_base as (
    select
        product_id,
        min(product_name) as product_name,
        min(category) as category,
        sum(line_revenue) as revenue,
        sum(line_list_revenue) as list_revenue,
        avg(discount_depth) as avg_discount_pct,
        sum(gross_margin_value) as gross_margin_value,
        cast(avg(high_discount_flag) as double) as high_discount_share,
        count(*) as order_item_count
    from int_order_item_pricing_metrics
    group by 1
)
select
    product_id,
    product_name,
    category,
    revenue,
    list_revenue,
    avg_discount_pct,
    case
        when revenue > 0 then gross_margin_value / revenue
        else null
    end as avg_margin_proxy_pct,
    high_discount_share,
    order_item_count,
    case
        when list_revenue > 0 then revenue / list_revenue
        else null
    end as price_realization
from product_base
order by revenue desc;
