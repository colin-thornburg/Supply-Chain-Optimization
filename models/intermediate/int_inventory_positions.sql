with inventory_snapshots as (

    select *
    from {{ ref('stg_wms__inventory_snapshots') }}

),

products as (

    select sku, standard_unit_cost
    from {{ ref('stg_erp__products') }}

),

final as (

    select
        inventory_snapshots.inventory_snapshot_key,
        inventory_snapshots.snapshot_date,
        inventory_snapshots.location_id,
        inventory_snapshots.sku,
        inventory_snapshots.on_hand_qty,
        inventory_snapshots.allocated_qty,
        inventory_snapshots.on_order_qty,
        inventory_snapshots.in_transit_qty,
        inventory_snapshots.current_safety_stock_qty,
        inventory_snapshots.current_reorder_point,
        inventory_snapshots.current_reorder_qty,
        inventory_snapshots.last_count_date,
        products.standard_unit_cost,
        inventory_snapshots.on_hand_qty - inventory_snapshots.allocated_qty as available_to_promise_qty,
        inventory_snapshots.on_hand_qty + inventory_snapshots.on_order_qty + inventory_snapshots.in_transit_qty - inventory_snapshots.allocated_qty as total_inventory_position_qty,
        (inventory_snapshots.on_hand_qty * products.standard_unit_cost)::number(18, 4) as on_hand_value,
        ((inventory_snapshots.on_hand_qty + inventory_snapshots.on_order_qty + inventory_snapshots.in_transit_qty - inventory_snapshots.allocated_qty) * products.standard_unit_cost)::number(18, 4) as inventory_position_value,
        (inventory_snapshots.on_order_qty * products.standard_unit_cost)::number(18, 4) as on_order_value
    from inventory_snapshots
    inner join products using (sku)

)

select *
from final
