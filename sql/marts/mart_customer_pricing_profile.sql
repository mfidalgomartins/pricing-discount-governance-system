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
        case
            when high_discount_order = 1
             and coalesce(
                    lag(high_discount_order) over (
                        partition by customer_id
                        order by order_date, order_id
                    ),
                    0
                 ) = 1 then 1
            else 0
        end as repeat_high_discount_pair
    from order_level
),
repeat_behavior as (
    select
        customer_id,
        -- Regra de negocio: mede pares consecutivos de encomendas com desconto alto.
        case
            when count(*) > 1 then cast(sum(repeat_high_discount_pair) as double) / (count(*) - 1)
            else 0
        end as repeat_discount_behavior
    from order_sequence
    group by 1
),
order_stats as (
    select
        customer_id,
        cast(avg(discounted_order) as double) as share_orders_discounted,
        cast(avg(high_discount_order) as double) as share_orders_high_discount
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
        sum(line_list_revenue) as total_list_revenue,
        sum(discount_depth * line_list_revenue) as weighted_discount_value,
        cast(avg(discounted_flag) as double) as share_order_items_discounted,
        sum(case when high_discount_flag = 1 then line_revenue else 0 end) as revenue_high_discount,
        count(distinct product_id) as product_diversity,
        sum(gross_margin_value) as gross_margin_value,
        stddev_pop(realized_price) / nullif(avg(realized_price), 0) as realized_price_cv,
        avg(abs_price_realization_residual_pct) as avg_abs_price_realization_residual_pct
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
    case
        when cb.total_list_revenue > 0 then cb.weighted_discount_value / cb.total_list_revenue
        else 0
    end as weighted_discount_pct,
    cb.share_order_items_discounted,
    cb.product_diversity,
    case
        when cb.total_revenue > 0 then cb.gross_margin_value / cb.total_revenue
        else 0
    end as avg_margin_proxy_pct,
    coalesce(cb.realized_price_cv, 0.0) as realized_price_cv,
    coalesce(cb.avg_abs_price_realization_residual_pct, 0.0)
        as avg_abs_price_realization_residual_pct,
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
