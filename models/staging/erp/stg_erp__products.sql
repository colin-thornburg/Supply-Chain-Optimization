with source_data as (

    select *
    from {{ source('erp', 'products') }}

),

casted as (

    select
        trim(sku)::varchar as sku,
        trim(product_name)::varchar as product_name,
        trim(category)::varchar as category,
        trim(subcategory)::varchar as subcategory,
        trim(brand)::varchar as brand,
        is_private_label::boolean as is_private_label,
        trim(unit_of_measure)::varchar as unit_of_measure,
        pack_qty::number(18, 0) as pack_qty,
        standard_unit_cost::number(18, 4) as standard_unit_cost,
        list_price::number(18, 4) as list_price,
        trim(abc_class)::varchar as abc_class,
        trim(xyz_class)::varchar as xyz_class,
        is_hazmat::boolean as is_hazmat,
        weight_lbs::number(18, 4) as weight_lbs,
        cube_cuft::number(18, 4) as cube_cuft,
        trim(lifecycle_status)::varchar as lifecycle_status,
        first_sold_date::date as first_sold_date
    from source_data

)

select *
from casted
