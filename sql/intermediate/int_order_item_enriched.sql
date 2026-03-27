create or replace view int_order_item_enriched as
select
    oi.order_item_id,
    oi.order_id,
    o.customer_id,
    o.order_date,
    o.sales_channel,
    o.sales_rep_id,
    oi.product_id,
    oi.quantity,
    oi.list_price_at_sale,
    oi.realized_unit_price,
    oi.discount_pct,
    c.signup_date,
    c.segment,
    c.region,
    c.company_size,
    p.product_name,
    p.category,
    p.list_price,
    p.unit_cost,
    sr.team,
    sr.rep_region,
    date_diff('day', c.signup_date, o.order_date) as days_since_signup
from stg_order_items oi
inner join stg_orders o
    on oi.order_id = o.order_id
inner join stg_customers c
    on o.customer_id = c.customer_id
inner join stg_products p
    on oi.product_id = p.product_id
left join stg_sales_reps sr
    on o.sales_rep_id = sr.sales_rep_id;
