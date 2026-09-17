with source_data as (

    select *
    from {{ source('erp', 'sales_orders') }}

),

casted as (

    select
        trim(order_id)::varchar as order_id,
        trim(customer_id)::varchar as customer_id,
        trim(fulfilling_location_id)::varchar as fulfilling_location_id,
        trim(order_channel)::varchar as order_channel,
        ordered_at::timestamp_ntz as ordered_at,
        requested_ship_date::date as requested_ship_date,
        trim(order_status)::varchar as order_status
    from source_data

)

select *
from casted
