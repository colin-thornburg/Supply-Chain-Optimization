with source_data as (

    select *
    from {{ source('wms', 'transfer_orders') }}

),

casted as (

    select
        trim(transfer_id)::varchar as transfer_id,
        trim(sku)::varchar as sku,
        trim(from_location_id)::varchar as from_location_id,
        trim(to_location_id)::varchar as to_location_id,
        qty::number(18, 0) as qty,
        created_at::timestamp_ntz as created_at,
        shipped_at::timestamp_ntz as shipped_at,
        received_at::timestamp_ntz as received_at,
        trim(status)::varchar as status
    from source_data

)

select *
from casted
