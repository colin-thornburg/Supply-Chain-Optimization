with source_data as (

    select *
    from {{ source('erp', 'purchase_order_lines') }}

),

casted as (

    select
        trim(po_line_id)::varchar as po_line_id,
        trim(po_id)::varchar as po_id,
        trim(sku)::varchar as sku,
        ordered_qty::number(18, 0) as ordered_qty,
        received_qty::number(18, 0) as received_qty,
        unit_cost::number(18, 4) as unit_cost,
        received_at::timestamp_ntz as received_at
    from source_data

)

select *
from casted
