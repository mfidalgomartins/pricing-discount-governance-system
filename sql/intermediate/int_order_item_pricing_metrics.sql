create or replace table int_order_item_pricing_metrics as
with policy as (
    select
        max(high_discount_threshold) as high_discount_threshold,
        max(discounted_threshold) as discounted_threshold
    from policy_thresholds
),
base as (
    select
        e.order_item_id,
        e.order_id,
        e.customer_id,
        e.order_date,
        cast(date_trunc('month', e.order_date) as date) as order_month,
        concat(
            cast(extract(year from e.order_date) as varchar),
            '-Q',
            cast(extract(quarter from e.order_date) as varchar)
        ) as order_quarter,
        e.sales_channel,
        e.sales_rep_id,
        e.product_id,
        e.quantity,
        e.list_price_at_sale,
        e.realized_unit_price,
        e.discount_pct,
        e.signup_date,
        e.segment,
        e.region,
        e.company_size,
        e.product_name,
        e.category,
        e.list_price,
        e.unit_cost,
        e.team,
        e.rep_region,
        e.days_since_signup,
        e.realized_unit_price as realized_price,
        e.discount_pct as discount_depth,
        case
            when e.list_price_at_sale > 0
                then e.realized_unit_price / e.list_price_at_sale
            else null
        end as line_price_realization
    from int_order_item_enriched e
),
line_financials as (
    select
        b.*,
        b.quantity * b.list_price_at_sale as line_list_revenue,
        b.quantity * b.realized_price as line_revenue,
        b.quantity * b.unit_cost as line_cost
    from base b
),
pricing_metrics as (
    select
        lf.*,
        lf.line_revenue - lf.line_cost as gross_margin_value,
        avg(lf.line_price_realization) over (
            partition by lf.product_id, lf.sales_channel
        ) as product_channel_avg_price_realization
    from line_financials lf
),
pricing_residuals as (
    select
        pm.*,
        case
            when pm.product_channel_avg_price_realization > 0
                then (pm.line_price_realization - pm.product_channel_avg_price_realization)
                    / pm.product_channel_avg_price_realization
            else 0.0
        end as price_realization_residual_pct
    from pricing_metrics pm
)
select
    pr.order_item_id,
    pr.order_id,
    pr.customer_id,
    pr.order_date,
    pr.order_month,
    pr.order_quarter,
    pr.sales_channel,
    pr.sales_rep_id,
    pr.product_id,
    pr.quantity,
    pr.list_price_at_sale,
    pr.realized_unit_price,
    pr.discount_pct,
    pr.signup_date,
    pr.segment,
    pr.region,
    pr.company_size,
    pr.product_name,
    pr.category,
    pr.list_price,
    pr.unit_cost,
    pr.team,
    pr.rep_region,
    pr.days_since_signup,
    pr.realized_price,
    pr.discount_depth,
    pr.line_price_realization,
    -- Regra de negocio: buckets sao fechados no limite superior, alinhados com pandas.cut.
    case
        when pr.discount_depth is null then null
        when pr.discount_depth <= 0.05 then '0-5%'
        when pr.discount_depth <= 0.10 then '5-10%'
        when pr.discount_depth <= 0.20 then '10-20%'
        when pr.discount_depth <= 0.30 then '20-30%'
        else '30%+'
    end as discount_bucket,
    pr.line_list_revenue,
    pr.line_revenue,
    pr.line_cost,
    pr.gross_margin_value,
    case
        when pr.line_revenue > 0
            then pr.gross_margin_value / pr.line_revenue
        else null
    end as margin_proxy_pct,
    pr.price_realization_residual_pct,
    abs(pr.price_realization_residual_pct) as abs_price_realization_residual_pct,
    case
        when pr.discount_depth >= policy.high_discount_threshold then 1
        else 0
    end as high_discount_flag,
    case
        when pr.discount_depth >= policy.discounted_threshold then 1
        else 0
    end as discounted_flag
from pricing_residuals pr
cross join policy;
