with weekly_demand as (

    select
        {{ dbt_utils.generate_surrogate_key(['sku', 'location_id', "date_trunc('week', demand_date)"]) }} as sku_location_week_key,
        sku,
        location_id,
        date_trunc('week', demand_date)::date as demand_week,
        sum(gross_demand_qty) as gross_demand_qty,
        sum(net_shipped_qty) as net_shipped_qty,
        sum(backordered_qty) as backordered_qty,
        sum(substituted_qty) as substituted_qty
    from {{ ref('int_demand_daily_spine') }}
    group by 1, 2, 3, 4

),

weekly_lines as (

    select
        sku,
        location_id,
        date_trunc('week', ordered_at)::date as demand_week,
        count(*) as order_line_count,
        count_if(shipped_qty = ordered_qty and ordered_qty > 0) as shipped_line_count
    from {{ ref('fct_sales_order_lines') }}
    group by 1, 2, 3

),

variability as (

    select *
    from {{ ref('int_demand_variability') }}

),

latest_policy as (

    select *
    from {{ ref('int_inventory_positions') }}
    qualify row_number() over (partition by sku, location_id order by snapshot_date desc) = 1

),

primary_supplier as (

    select *
    from {{ ref('stg_erp__supplier_products') }}
    where is_primary_source

),

supplier_reliability as (

    select *
    from {{ ref('int_supplier_reliability') }}

),

products as (

    select sku, category, abc_class
    from {{ ref('stg_erp__products') }}

)

select
    weekly_demand.sku_location_week_key,
    weekly_demand.sku,
    weekly_demand.location_id,
    weekly_demand.demand_week,
    products.category,
    products.abc_class,
    weekly_demand.gross_demand_qty,
    weekly_demand.net_shipped_qty,
    weekly_demand.backordered_qty,
    weekly_demand.substituted_qty,
    coalesce(weekly_lines.order_line_count, 0) as order_line_count,
    coalesce(weekly_lines.shipped_line_count, 0) as shipped_line_count,
    variability.mean_weekly_demand,
    variability.stddev_weekly_demand,
    variability.coefficient_of_variation,
    variability.average_demand_interval,
    variability.demand_class,
    latest_policy.current_safety_stock_qty,
    latest_policy.current_reorder_point,
    latest_policy.current_reorder_qty,
    primary_supplier.supplier_id as primary_supplier_id,
    coalesce(supplier_reliability.mean_actual_lead_time_days, primary_supplier.quoted_lead_time_days)::number(18, 4) as mean_lead_time_days,
    coalesce(supplier_reliability.stddev_actual_lead_time_days, 0)::number(18, 4) as stddev_lead_time_days,
    coalesce(supplier_reliability.is_reliable_sample, false) as is_reliable_lead_time_sample
from weekly_demand
inner join variability using (sku, location_id)
inner join products using (sku)
left join weekly_lines using (sku, location_id, demand_week)
left join latest_policy using (sku, location_id)
left join primary_supplier using (sku)
left join supplier_reliability
    on primary_supplier.supplier_id = supplier_reliability.supplier_id
    and weekly_demand.sku = supplier_reliability.sku
