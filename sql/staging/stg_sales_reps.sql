create or replace view stg_sales_reps as
select
    sales_rep_id,
    team,
    region as rep_region
from raw_sales_reps
where sales_rep_id is not null;
