create or replace table mart_overall_pricing_health as
with portfolio_base as (
    select
        cast(max(order_date) as date) as as_of_date,
        sum(line_revenue) as total_revenue,
        sum(line_list_revenue) as total_list_revenue,
        sum(gross_margin_value) as total_margin_proxy_value,
        avg(discount_depth) as avg_realized_discount,
        sum(case when high_discount_flag = 1 then line_revenue else 0 end) as high_discount_revenue
    from int_order_item_pricing_metrics
)
select
    as_of_date,
    total_revenue,
    total_list_revenue,
    total_margin_proxy_value,
    avg_realized_discount,
    case
        when total_list_revenue > 0 then 1 - (total_revenue / total_list_revenue)
        else null
    end as weighted_realized_discount,
    case
        when total_revenue > 0 then high_discount_revenue / total_revenue
        else null
    end as high_discount_revenue_share,
    case
        when total_list_revenue > 0 then total_revenue / total_list_revenue
        else null
    end as price_realization,
    case
        when total_revenue > 0 then total_margin_proxy_value / total_revenue
        else null
    end as margin_proxy_pct
from portfolio_base;
