create or replace table mart_customer_pricing_profile as
with order_level as (
    select
        customer_id,
        order_id,
        order_date,
        sum(line_revenue) as order_revenue,
        avg(discount_depth) as order_discount_depth,
        max(high_discount_flag) as high_discount_order,
        max(discounted_flag) as discounted_order
    from int_order_item_pricing_metrics
    group by 1, 2, 3
),
order_sequence as (
    select
        customer_id,
        order_id,
        order_date,
        high_discount_order,
        lag(high_discount_order) over (
            partition by customer_id
            order by order_date, order_id
        ) as prev_high_discount_order
    from order_level
),
repeat_behavior as (
    select
        customer_id,
        case
            when count(*) > 1 then
                sum(
                    case
                        when high_discount_order = 1
                         and coalesce(prev_high_discount_order, 0) = 1 then 1
                        else 0
                    end
                )::double / (count(*) - 1)
            else 0
        end as repeat_discount_behavior
    from order_sequence
    group by 1
),
order_stats as (
    select
        customer_id,
        avg(discounted_order)::double as share_orders_discounted,
        avg(high_discount_order)::double as share_orders_high_discount
    from order_level
    group by 1
),
customer_base as (
    select
        customer_id,
        min(segment) as segment,
        min(region) as region,
        min(company_size) as company_size,
        count(distinct order_id) as total_orders,
        count(*) as total_order_items,
        sum(line_revenue) as total_revenue,
        avg(discount_depth) as avg_discount_pct,
        sum(discount_depth * line_list_revenue) / nullif(sum(line_list_revenue), 0) as weighted_discount_pct,
        avg(discounted_flag)::double as share_order_items_discounted,
        sum(case when high_discount_flag = 1 then line_revenue else 0 end) as revenue_high_discount,
        count(distinct product_id) as product_diversity,
        avg(margin_proxy_pct) as avg_margin_proxy_pct,
        stddev_pop(realized_price) / nullif(avg(realized_price), 0) as realized_price_cv
    from int_order_item_pricing_metrics
    group by 1
)
select
    cb.customer_id,
    cb.segment,
    cb.region,
    cb.company_size,
    cb.total_orders,
    cb.total_order_items,
    cb.total_revenue,
    cb.avg_discount_pct,
    cb.weighted_discount_pct,
    cb.share_order_items_discounted,
    cb.product_diversity,
    cb.avg_margin_proxy_pct,
    coalesce(cb.realized_price_cv, 0.0) as realized_price_cv,
    coalesce(os.share_orders_discounted, 0.0) as share_orders_discounted,
    coalesce(os.share_orders_high_discount, 0.0) as share_orders_high_discount,
    coalesce(rb.repeat_discount_behavior, 0.0) as repeat_discount_behavior,
    case
        when cb.total_revenue > 0 then cb.revenue_high_discount / cb.total_revenue
        else 0
    end as revenue_high_discount_share
from customer_base cb
left join order_stats os
    on cb.customer_id = os.customer_id
left join repeat_behavior rb
    on cb.customer_id = rb.customer_id
order by cb.total_revenue desc;
