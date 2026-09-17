with source_data as (

    select *
    from {{ source('erp', 'product_substitutes') }}

),

casted as (

    select
        {{ dbt_utils.generate_surrogate_key(['sku', 'substitute_sku']) }} as product_substitute_key,
        trim(sku)::varchar as sku,
        trim(substitute_sku)::varchar as substitute_sku,
        trim(substitution_type)::varchar as substitution_type,
        preference_rank::number(18, 0) as preference_rank
    from source_data

)

select *
from casted
