select
    po_line_id,
    po_id,
    supplier_id,
    sku,
    location_id,
    ordered_at,
    promised_date,
    received_at,
    ordered_qty,
    received_qty,
    unit_cost,
    quoted_lead_time_days,
    actual_lead_time_days,
    lead_time_variance_days,
    is_on_time,
    fill_reliability,
    (greatest(ordered_qty - received_qty, 0) * unit_cost)::number(18, 4) as open_po_value
from {{ ref('int_lead_time_actuals') }}
