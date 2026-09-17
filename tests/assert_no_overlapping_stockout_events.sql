select
    left_event.stockout_event_key as left_event_key,
    right_event.stockout_event_key as right_event_key
from {{ ref('fct_stockout_events') }} as left_event
inner join {{ ref('fct_stockout_events') }} as right_event
    on left_event.sku = right_event.sku
    and left_event.location_id = right_event.location_id
    and left_event.stockout_event_key < right_event.stockout_event_key
    and left_event.stockout_start_date <= right_event.stockout_end_date
    and right_event.stockout_start_date <= left_event.stockout_end_date
