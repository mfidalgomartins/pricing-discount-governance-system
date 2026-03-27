create or replace view stg_customers as
select
    customer_id,
    cast(signup_date as date) as signup_date,
    segment,
    region,
    company_size
from raw_customers
where customer_id is not null;
