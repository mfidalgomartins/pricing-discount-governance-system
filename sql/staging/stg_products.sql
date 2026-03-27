create or replace view stg_products as
select
    product_id,
    product_name,
    category,
    cast(list_price as double) as list_price,
    cast(unit_cost as double) as unit_cost
from raw_products
where product_id is not null;
