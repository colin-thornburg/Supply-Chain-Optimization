with sales_order_lines as (

    select *
    from {{ ref('stg_erp__sales_order_lines') }}

),

sales_orders as (

    select *
    from {{ ref('stg_erp__sales_orders') }}

),

final as (

    select
        sales_order_lines.order_line_id,
        sales_order_lines.order_id,
        sales_order_lines.sku,
        sales_orders.fulfilling_location_id as location_id,
        sales_orders.customer_id,
        sales_orders.order_channel,
        sales_orders.ordered_at,
        sales_orders.ordered_at::date as demand_date,
        sales_order_lines.line_status,
        case when sales_order_lines.line_status = 'cancelled' then 0 else sales_order_lines.ordered_qty end as gross_demand_qty,
        sales_order_lines.shipped_qty as net_shipped_qty,
        case
            when sales_order_lines.line_status in ('backordered', 'shipped_partial')
                then greatest(sales_order_lines.ordered_qty - sales_order_lines.shipped_qty, 0)
            else 0
        end as backordered_qty,
        case when sales_order_lines.line_status = 'substituted' then sales_order_lines.ordered_qty else 0 end as substituted_qty
    from sales_order_lines
    inner join sales_orders using (order_id)

)

select *
from final
