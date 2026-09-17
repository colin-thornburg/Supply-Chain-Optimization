with calendar_dates as (

    {{ dbt_date.get_date_dimension('2024-07-01', '2026-06-30') }}

),

products as (

    select sku, first_sold_date
    from {{ ref('stg_erp__products') }}

),

locations as (

    select location_id, opened_date
    from {{ ref('stg_wms__locations') }}
    where is_active

),

daily_demand as (

    select
        sku,
        location_id,
        demand_date,
        sum(gross_demand_qty) as gross_demand_qty,
        sum(net_shipped_qty) as net_shipped_qty,
        sum(backordered_qty) as backordered_qty,
        sum(substituted_qty) as substituted_qty
    from {{ ref('int_demand_gross_vs_net') }}
    group by 1, 2, 3

),

densified as (

    select
        products.sku,
        locations.location_id,
        calendar_dates.date_day as demand_date,
        coalesce(daily_demand.gross_demand_qty, 0)::number(18, 0) as gross_demand_qty,
        coalesce(daily_demand.net_shipped_qty, 0)::number(18, 0) as net_shipped_qty,
        coalesce(daily_demand.backordered_qty, 0)::number(18, 0) as backordered_qty,
        coalesce(daily_demand.substituted_qty, 0)::number(18, 0) as substituted_qty
    from calendar_dates
    cross join products
    cross join locations
    left join daily_demand
        on products.sku = daily_demand.sku
        and locations.location_id = daily_demand.location_id
        and calendar_dates.date_day = daily_demand.demand_date
    where calendar_dates.date_day >= greatest(products.first_sold_date, locations.opened_date, '2024-07-01'::date)

)

select *
from densified
