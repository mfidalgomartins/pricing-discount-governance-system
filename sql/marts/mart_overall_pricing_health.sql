create or replace table mart_overall_pricing_health as
select
    current_date as as_of_date,
    sum(line_revenue) as total_revenue,
    sum(line_list_revenue) as total_list_revenue,
    sum(gross_margin_value) as total_margin_proxy_value,
    avg(discount_depth) as avg_realized_discount,
    case
        when sum(line_list_revenue) > 0 then 1 - (sum(line_revenue) / sum(line_list_revenue))
        else null
    end as weighted_realized_discount,
    case
        when sum(line_revenue) > 0 then
            sum(case when high_discount_flag = 1 then line_revenue else 0 end) / sum(line_revenue)
        else null
    end as high_discount_revenue_share,
    case
        when sum(line_list_revenue) > 0 then sum(line_revenue) / sum(line_list_revenue)
        else null
    end as price_realization,
    case
        when sum(line_revenue) > 0 then sum(gross_margin_value) / sum(line_revenue)
        else null
    end as margin_proxy_pct
from int_order_item_pricing_metrics;
