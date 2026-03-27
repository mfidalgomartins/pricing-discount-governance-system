create or replace table mart_product_pricing_summary as
select
    product_id,
    min(product_name) as product_name,
    min(category) as category,
    sum(line_revenue) as revenue,
    sum(line_list_revenue) as list_revenue,
    avg(discount_depth) as avg_discount_pct,
    avg(margin_proxy_pct) as avg_margin_proxy_pct,
    avg(high_discount_flag)::double as high_discount_share,
    count(*) as order_item_count,
    case
        when sum(line_list_revenue) > 0 then sum(line_revenue) / sum(line_list_revenue)
        else null
    end as price_realization
from int_order_item_pricing_metrics
group by 1
order by revenue desc;
