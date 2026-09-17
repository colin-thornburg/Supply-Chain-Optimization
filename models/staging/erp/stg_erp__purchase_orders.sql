with source_data as (

    select *
    from {{ source('erp', 'purchase_orders') }}

),

casted as (

    select
        trim(po_id)::varchar as po_id,
        trim(supplier_id)::varchar as supplier_id,
        trim(destination_location_id)::varchar as destination_location_id,
        ordered_at::timestamp_ntz as ordered_at,
        promised_date::date as promised_date,
        trim(po_status)::varchar as po_status
    from source_data

)

select *
from casted
