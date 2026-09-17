with source_data as (

    select *
    from {{ source('erp', 'customers') }}

),

casted as (

    select
        trim(customer_id)::varchar as customer_id,
        trim(customer_name)::varchar as customer_name,
        trim(industry_segment)::varchar as industry_segment,
        trim(size_tier)::varchar as size_tier,
        trim(contract_type)::varchar as contract_type,
        is_onsite_program::boolean as is_onsite_program,
        trim(primary_location_id)::varchar as primary_location_id,
        first_order_date::date as first_order_date
    from source_data

)

select *
from casted
