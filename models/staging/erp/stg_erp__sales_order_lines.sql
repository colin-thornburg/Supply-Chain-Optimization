with source_data as (

    select *
    from {{ source('erp', 'sales_order_lines') }}

),

casted as (

    select
        trim(order_line_id)::varchar as order_line_id,
        trim(order_id)::varchar as order_id,
        trim(sku)::varchar as sku,
        ordered_qty::number(18, 0) as ordered_qty,
        shipped_qty::number(18, 0) as shipped_qty,
        unit_price::number(18, 4) as unit_price,
        unit_cost::number(18, 4) as unit_cost,
        trim(line_status)::varchar as line_status,
        shipped_at::timestamp_ntz as shipped_at,
        nullif(trim(substituted_sku), '')::varchar as substituted_sku
    from source_data

)

select *
from casted
