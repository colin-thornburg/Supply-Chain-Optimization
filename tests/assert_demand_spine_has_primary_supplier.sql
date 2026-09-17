select distinct demand.sku, demand.location_id
from {{ ref('int_demand_daily_spine') }} as demand
left join {{ ref('stg_erp__supplier_products') }} as supplier_products
    on demand.sku = supplier_products.sku
    and supplier_products.is_primary_source
where supplier_products.supplier_id is null
