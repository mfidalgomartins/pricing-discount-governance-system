create or replace table mart_segment_channel_diagnostics as
select
    segment,
    sales_channel,
    sum(line_revenue) as revenue,
    avg(discount_depth) as avg_discount_pct,
    avg(margin_proxy_pct) as avg_margin_proxy_pct,
    avg(high_discount_flag)::double as high_discount_share,
    count(*) as order_item_count
from int_order_item_pricing_metrics
group by 1, 2
order by segment, avg_discount_pct desc;
