{{
    config(
        materialized='incremental',
        unique_key='inventory_snapshot_key',
        incremental_strategy='merge'
    )
}}

-- Snowflake MERGE is keyed by the deterministic SKU-location-date hash so late
-- corrections replace a snapshot instead of duplicating it.
with inventory_positions as (

    select *
    from {{ ref('int_inventory_positions') }}

    {% if is_incremental() %}
    where snapshot_date >= (select coalesce(max(snapshot_date), '1900-01-01'::date) from {{ this }})
    {% endif %}

),

demand_history as (

    select *
    from {{ ref('int_demand_daily_spine') }}

),

inventory_with_demand as (

    select
        inventory_positions.*,
        coalesce(sum(demand_history.gross_demand_qty), 0) as trailing_26_week_demand_qty
    from inventory_positions
    left join demand_history
        on inventory_positions.sku = demand_history.sku
        and inventory_positions.location_id = demand_history.location_id
        and demand_history.demand_date between dateadd('week', -26, inventory_positions.snapshot_date) and inventory_positions.snapshot_date
    group by all

)

select
    *,
    on_hand_qty > 0 and trailing_26_week_demand_qty = 0 as is_excess_or_obsolete,
    case
        when on_hand_qty > 0 and trailing_26_week_demand_qty = 0 then on_hand_value
        else 0
    end::number(18, 4) as excess_obsolete_on_hand_value
from inventory_with_demand
