with source_data as (

    select *
    from {{ source('erp', 'suppliers') }}

),

casted as (

    select
        trim(supplier_id)::varchar as supplier_id,
        trim(supplier_name)::varchar as supplier_name,
        trim(supplier_country)::varchar as supplier_country,
        trim(sourcing_region)::varchar as sourcing_region,
        payment_terms_days::number(18, 0) as payment_terms_days,
        is_private_label_manufacturer::boolean as is_private_label_manufacturer,
        quality_rating::number(18, 4) as quality_rating
    from source_data

)

select *
from casted
