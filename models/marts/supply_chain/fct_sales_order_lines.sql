{{
    config(
        materialized='incremental',
        unique_key='order_line_id',
        incremental_strategy='merge'
    )
}}

-- Snowflake MERGE updates corrected source lines and inserts new immutable line IDs
-- without rebuilding order history, which mirrors the production landing pattern.
with demand as (

    select *
    from {{ ref('int_demand_gross_vs_net') }}

),

lines as (

    select *
    from {{ ref('stg_erp__sales_order_lines') }}

),

orders as (

    select order_id, requested_ship_date
    from {{ ref('stg_erp__sales_orders') }}

)

select
    demand.order_line_id,
    {{ dbt_utils.generate_surrogate_key(['demand.sku', 'demand.location_id']) }} as sku_location_key,
    demand.order_id,
    demand.sku,
    demand.location_id,
    demand.customer_id,
    demand.ordered_at,
    orders.requested_ship_date,
    demand.order_channel,
    demand.line_status,
    lines.ordered_qty,
    demand.gross_demand_qty,
    lines.shipped_qty,
    demand.backordered_qty,
    demand.substituted_qty,
    (lines.shipped_qty = lines.ordered_qty and lines.ordered_qty > 0)::boolean as is_line_filled,
    lines.unit_price,
    lines.unit_cost,
    lines.shipped_at,
    lines.substituted_sku,
    (lines.shipped_qty * lines.unit_price)::number(18, 4) as net_sales,
    (lines.shipped_qty * lines.unit_cost)::number(18, 4) as cost_of_goods


from demand
inner join lines on demand.order_line_id = lines.order_line_id
inner join orders on demand.order_id = orders.order_id


{% if is_incremental() %}
where demand.ordered_at >= (select coalesce(max(ordered_at), '1900-01-01'::timestamp_ntz) from {{ this }})
{% endif %}
