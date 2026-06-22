create or replace table mart_monthly_pricing_health as
with monthly_base as (
    select
        order_month,
        sum(line_revenue) as revenue,
        sum(line_list_revenue) as list_revenue,
        sum(gross_margin_value) as gross_margin_value,
        avg(discount_depth) as avg_discount_pct,
        cast(avg(high_discount_flag) as double) as high_discount_share
    from int_order_item_pricing_metrics
    group by 1
)
select
    order_month,
    revenue,
    list_revenue,
    gross_margin_value,
    avg_discount_pct,
    high_discount_share,
    case
        when list_revenue > 0 then 1 - (revenue / list_revenue)
        else null
    end as weighted_discount_pct,
    case
        when revenue > 0 then gross_margin_value / revenue
        else null
    end as margin_proxy_pct
from monthly_base
order by order_month;
