create or replace view stg_order_items as
select
    order_item_id,
    order_id,
    product_id,
    cast(quantity as bigint) as quantity,
    cast(list_price_at_sale as double) as list_price_at_sale,
    cast(realized_unit_price as double) as realized_unit_price,
    cast(discount_pct as double) as discount_pct
from raw_order_items
where order_item_id is not null;
