with purchase_order_lines as (

    select *
    from {{ ref('fct_purchase_order_lines') }}

)

select
    supplier_id,
    count(*) as po_line_count,
    count_if(is_on_time) as on_time_po_line_count,
    avg(actual_lead_time_days)::number(18, 4) as mean_actual_lead_time_days,
    coalesce(stddev_samp(actual_lead_time_days), 0)::number(18, 4) as stddev_actual_lead_time_days,
    count_if(is_on_time) / nullif(count_if(received_at is not null), 0)::number(18, 4) as supplier_on_time_rate,
    sum(received_qty) / nullif(sum(ordered_qty), 0)::number(18, 4) as supplier_fill_rate,
    sum(open_po_value)::number(18, 4) as open_po_value,
    count_if(received_at is not null) >= 5 as is_reliable_sample
from purchase_order_lines
group by 1
