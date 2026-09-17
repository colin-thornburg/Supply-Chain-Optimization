with source_data as (

    select *
    from {{ source('erp', 'supplier_products') }}

),

casted as (

    select
        {{ dbt_utils.generate_surrogate_key(['supplier_id', 'sku']) }} as supplier_product_key,
        trim(supplier_id)::varchar as supplier_id,
        trim(sku)::varchar as sku,
        is_primary_source::boolean as is_primary_source,
        quoted_lead_time_days::number(18, 0) as quoted_lead_time_days,
        min_order_qty::number(18, 0) as min_order_qty,
        order_multiple::number(18, 0) as order_multiple,
        unit_cost::number(18, 4) as unit_cost,
        effective_from_date::date as effective_from_date
    from source_data

)

select *
from casted
