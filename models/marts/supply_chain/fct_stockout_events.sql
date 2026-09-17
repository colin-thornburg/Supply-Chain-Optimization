select *
from {{ ref('int_stockout_events') }}
