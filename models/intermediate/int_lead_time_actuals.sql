with purchase_order_lines as (

    select *
    from {{ ref('stg_erp__purchase_order_lines') }}

),

purchase_orders as (

    select *
    from {{ ref('stg_erp__purchase_orders') }}

),

supplier_products as (

    select *
    from {{ ref('stg_erp__supplier_products') }}
    where is_primary_source

),

final as (

    select
        purchase_order_lines.po_line_id,
        purchase_order_lines.po_id,
        purchase_order_lines.sku,
        purchase_orders.supplier_id,
        purchase_orders.destination_location_id as location_id,
        purchase_orders.ordered_at,
        purchase_orders.promised_date,
        purchase_order_lines.received_at,
        purchase_order_lines.ordered_qty,
        purchase_order_lines.received_qty,
        purchase_order_lines.unit_cost,
        supplier_products.quoted_lead_time_days,
        datediff('day', purchase_orders.ordered_at::date, purchase_order_lines.received_at::date) as actual_lead_time_days,
        datediff('day', purchase_orders.ordered_at::date, purchase_order_lines.received_at::date) - supplier_products.quoted_lead_time_days as lead_time_variance_days,
        case when purchase_order_lines.received_at is null then null else purchase_order_lines.received_at::date <= purchase_orders.promised_date end as is_on_time,
        case when purchase_order_lines.ordered_qty > 0 then least(purchase_order_lines.received_qty / purchase_order_lines.ordered_qty, 1.0) end::number(18, 4) as fill_reliability
    from purchase_order_lines
    inner join purchase_orders using (po_id)
    left join supplier_products
        on purchase_orders.supplier_id = supplier_products.supplier_id
        and purchase_order_lines.sku = supplier_products.sku

)

select *
from final
