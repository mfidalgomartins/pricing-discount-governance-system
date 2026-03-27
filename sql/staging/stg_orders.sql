create or replace view stg_orders as
select
    order_id,
    customer_id,
    cast(order_date as date) as order_date,
    sales_channel,
    sales_rep_id
from raw_orders
where order_id is not null;
