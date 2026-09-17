with actuals as (

    select *
    from {{ ref('int_lead_time_actuals') }}
    where received_at is not null

),

aggregated as (

    select
        supplier_id,
        sku,
        count(*) as received_po_line_count,
        avg(actual_lead_time_days)::number(18, 4) as mean_actual_lead_time_days,
        coalesce(stddev_samp(actual_lead_time_days), 0)::number(18, 4) as stddev_actual_lead_time_days,
        avg(iff(is_on_time, 1, 0))::number(18, 4) as on_time_rate,
        sum(received_qty) / nullif(sum(ordered_qty), 0)::number(18, 4) as fill_rate,
        count(*) >= 5 as is_reliable_sample
    from actuals
    group by 1, 2

)

select *
from aggregated
