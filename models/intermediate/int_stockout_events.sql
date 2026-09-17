with zero_positions as (

    select
        sku,
        location_id,
        snapshot_date,
        row_number() over (partition by sku, location_id order by snapshot_date) as zero_sequence,
        datediff('day', '2000-01-03'::date, snapshot_date) / 7 as week_sequence
    from {{ ref('int_inventory_positions') }}
    where available_to_promise_qty <= 0

),

islands as (

    select
        *,
        week_sequence - zero_sequence as event_group
    from zero_positions

),

event_windows as (

    select
        sku,
        location_id,
        event_group,
        min(snapshot_date) as stockout_start_date,
        dateadd('day', 6, max(snapshot_date))::date as stockout_end_date
    from islands
    group by 1, 2, 3

),

demand as (

    select *
    from {{ ref('int_demand_daily_spine') }}

),

final as (

    select
        {{ dbt_utils.generate_surrogate_key(['event_windows.sku', 'event_windows.location_id', 'event_windows.stockout_start_date']) }} as stockout_event_key,
        event_windows.sku,
        event_windows.location_id,
        event_windows.stockout_start_date,
        event_windows.stockout_end_date,
        datediff('day', event_windows.stockout_start_date, event_windows.stockout_end_date) + 1 as stockout_days,
        coalesce(sum(demand.gross_demand_qty), 0) as gross_demand_during_stockout_qty,
        coalesce(sum(demand.net_shipped_qty), 0) as shipped_during_stockout_qty
    from event_windows
    left join demand
        on event_windows.sku = demand.sku
        and event_windows.location_id = demand.location_id
        and demand.demand_date between event_windows.stockout_start_date and event_windows.stockout_end_date
    group by 1, 2, 3, 4, 5, 6

)

select *
from final
