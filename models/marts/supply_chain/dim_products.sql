with products as (

    select *
    from {{ ref('stg_erp__products') }}

),

substitution_chains as (

    select *
    from {{ ref('int_substitution_chains') }}

)

select
    products.*,
    substitution_chains.substitutable_group_sku,
    substitution_chains.maximum_chain_depth
from products
left join substitution_chains using (sku)
