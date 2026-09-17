with recommendations as (

    select *
    from {{ source('optimizer', 'policy_recommendations') }}

),

snapshots as (

    select
        sku,
        location_id,
        snapshot_date,
        current_safety_stock_qty,
        current_reorder_point,
        current_reorder_qty,
        on_hand_qty,
        on_hand_value
    from {{ ref('fct_inventory_snapshots') }}

)

select
    {{ dbt_utils.generate_surrogate_key(['recommendations.run_id', 'recommendations.sku', 'recommendations.location_id', 'snapshots.snapshot_date']) }} as policy_recommendation_impact_key,
    recommendations.run_id,
    recommendations.created_at,
    snapshots.snapshot_date,
    recommendations.sku,
    recommendations.location_id,
    recommendations.demand_class,
    recommendations.method,
    recommendations.recommended_safety_stock,
    recommendations.recommended_reorder_point,
    recommendations.recommended_order_qty,
    recommendations.current_safety_stock as safety_stock_at_run,
    snapshots.current_safety_stock_qty as actual_safety_stock,
    snapshots.current_reorder_point as actual_reorder_point,
    snapshots.current_reorder_qty as actual_reorder_qty,
    snapshots.on_hand_qty as actual_on_hand_qty,
    snapshots.on_hand_value as actual_on_hand_value,
    (recommendations.recommended_safety_stock - snapshots.current_safety_stock_qty)::number(18, 4) as safety_stock_gap_units,
    (recommendations.recommended_reorder_point - snapshots.current_reorder_point)::number(18, 4) as reorder_point_gap_units,
    (recommendations.recommended_order_qty - snapshots.current_reorder_qty)::number(18, 4) as order_qty_gap_units,
    snapshots.snapshot_date >= recommendations.created_at::date as is_after_recommendation
from recommendations
inner join snapshots
    on recommendations.sku = snapshots.sku
    and recommendations.location_id = snapshots.location_id
    and snapshots.snapshot_date >= recommendations.created_at::date
