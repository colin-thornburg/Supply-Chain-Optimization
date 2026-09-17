with sales as (

    select
        sku,
        location_id,
        count(*) as order_line_count,
        count_if(shipped_qty = ordered_qty and ordered_qty > 0) as shipped_line_count,
        sum(ordered_qty) as ordered_qty,
        sum(shipped_qty) as shipped_qty,
        count_if(line_status in ('backordered', 'shipped_partial')) as backordered_line_count,
        count_if(line_status = 'substituted') as substituted_line_count,
        sum(cost_of_goods) as annualized_cost_of_goods
    from {{ ref('fct_sales_order_lines') }}
    group by 1, 2

),

latest_inventory as (

    select *
    from {{ ref('fct_inventory_snapshots') }}
    qualify row_number() over (partition by sku, location_id order by snapshot_date desc) = 1

),

demand as (

    select
        sku,
        location_id,
        avg(gross_demand_qty)::number(18, 4) as average_daily_demand_qty,
        sum(iff(demand_date >= '2025-12-31'::date, gross_demand_qty, 0)) as trailing_26_week_demand_qty
    from {{ ref('int_demand_daily_spine') }}
    group by 1, 2

),

variability as (

    select sku, location_id, demand_class
    from {{ ref('int_demand_variability') }}

),

products as (

    select sku, category
    from {{ ref('stg_erp__products') }}

),

spine as (

    select distinct sku, location_id
    from {{ ref('int_demand_daily_spine') }}

)

select
    {{ dbt_utils.generate_surrogate_key(['spine.sku', 'spine.location_id']) }} as sku_location_key,
    spine.sku,
    spine.location_id,
    products.category,
    variability.demand_class,
    coalesce(sales.shipped_line_count / nullif(sales.order_line_count, 0), 0)::number(18, 4) as line_fill_rate,
    coalesce(sales.shipped_qty / nullif(sales.ordered_qty, 0), 0)::number(18, 4) as unit_fill_rate,
    coalesce(sales.backordered_line_count / nullif(sales.order_line_count, 0), 0)::number(18, 4) as backorder_rate,
    coalesce(sales.substituted_line_count / nullif(sales.order_line_count, 0), 0)::number(18, 4) as substitution_rate,
    latest_inventory.on_hand_qty / nullif(demand.average_daily_demand_qty, 0)::number(18, 4) as days_of_supply,
    sales.annualized_cost_of_goods / nullif(latest_inventory.on_hand_value, 0)::number(18, 4) as inventory_turns,
    coalesce(demand.trailing_26_week_demand_qty, 0) = 0 and coalesce(latest_inventory.on_hand_qty, 0) > 0 as is_excess_or_obsolete,
    coalesce(latest_inventory.on_hand_qty, 0) as on_hand_qty,
    coalesce(latest_inventory.on_hand_value, 0)::number(18, 4) as on_hand_value,
    coalesce(demand.trailing_26_week_demand_qty, 0) as trailing_26_week_demand_qty
from spine
left join sales using (sku, location_id)
left join latest_inventory using (sku, location_id)
left join demand using (sku, location_id)
left join variability using (sku, location_id)
left join products using (sku)
