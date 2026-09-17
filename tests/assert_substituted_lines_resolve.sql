select sales.order_line_id
from {{ ref('fct_sales_order_lines') }} as sales
left join {{ ref('dim_products') }} as products
    on sales.substituted_sku = products.sku
where sales.line_status = 'substituted'
  and (sales.substituted_sku is null or products.sku is null)
