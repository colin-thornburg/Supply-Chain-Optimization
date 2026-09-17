with source_data as (

    select *
    from {{ source('wms', 'inventory_snapshots') }}

),

casted as (

    select
        {{ dbt_utils.generate_surrogate_key(['snapshot_date', 'location_id', 'sku']) }} as inventory_snapshot_key,
        snapshot_date::date as snapshot_date,
        trim(location_id)::varchar as location_id,
        trim(sku)::varchar as sku,
        on_hand_qty::number(18, 0) as on_hand_qty,
        allocated_qty::number(18, 0) as allocated_qty,
        on_order_qty::number(18, 0) as on_order_qty,
        in_transit_qty::number(18, 0) as in_transit_qty,
        current_safety_stock_qty::number(18, 0) as current_safety_stock_qty,
        current_reorder_point::number(18, 0) as current_reorder_point,
        current_reorder_qty::number(18, 0) as current_reorder_qty,
        last_count_date::date as last_count_date
    from source_data

)

select *
from casted
