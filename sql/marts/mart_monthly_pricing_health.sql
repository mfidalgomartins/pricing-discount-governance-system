create or replace table mart_monthly_pricing_health as
select
    order_month,
    sum(line_revenue) as revenue,
    sum(line_list_revenue) as list_revenue,
    sum(gross_margin_value) as gross_margin_value,
    avg(discount_depth) as avg_discount_pct,
    avg(high_discount_flag)::double as high_discount_share,
    case
        when sum(line_list_revenue) > 0 then 1 - (sum(line_revenue) / sum(line_list_revenue))
        else null
    end as weighted_discount_pct,
    case
        when sum(line_revenue) > 0 then sum(gross_margin_value) / sum(line_revenue)
        else null
    end as margin_proxy_pct
from int_order_item_pricing_metrics
group by 1
order by order_month;
