select sku, location_id, demand_class
from {{ ref('int_demand_variability') }}
where demand_class is null
   or demand_class not in ('smooth', 'erratic', 'intermittent', 'lumpy')
