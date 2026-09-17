with recursive edges as (

    select sku as from_sku, substitute_sku as to_sku
    from {{ ref('stg_erp__product_substitutes') }}

    union all

    select substitute_sku as from_sku, sku as to_sku
    from {{ ref('stg_erp__product_substitutes') }}

),

walk (root_sku, reachable_sku, chain_depth) as (

    select sku, sku, 0
    from {{ ref('stg_erp__products') }}

    union all

    select
        walk.root_sku,
        edges.to_sku,
        walk.chain_depth + 1
    from walk
    inner join edges on walk.reachable_sku = edges.from_sku
    where walk.chain_depth < 10

),

final as (

    select
        root_sku as sku,
        min(reachable_sku) as substitutable_group_sku,
        max(chain_depth) as maximum_chain_depth
    from walk
    group by 1

)

select *
from final
