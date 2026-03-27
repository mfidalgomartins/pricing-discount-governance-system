create or replace table mart_segment_pricing_summary as
select
    segment,
    sum(line_revenue) as total_revenue,
    avg(discount_depth) as avg_discount_pct,
    median(discount_depth) as median_discount_pct,
    avg(high_discount_flag)::double as share_high_discount,
    avg(margin_proxy_pct) as avg_margin_proxy_pct,
    var_pop(realized_price) as realized_price_variance,
    stddev_pop(realized_price) as realized_price_std,
    (
        (1 - least(greatest(avg(margin_proxy_pct), 0), 1))
        * least(greatest(avg(high_discount_flag)::double, 0), 1)
        * 100
    ) as margin_erosion_proxy
from int_order_item_pricing_metrics
group by 1
order by margin_erosion_proxy desc;
