with weekly_demand as (

    select
        sku,
        location_id,
        date_trunc('week', demand_date)::date as demand_week,
        sum(gross_demand_qty) as weekly_demand_qty
    from {{ ref('int_demand_daily_spine') }}
    group by 1, 2, 3

),

statistics as (

    select
        sku,
        location_id,
        count(*) as observed_weeks,
        count_if(weekly_demand_qty > 0) as nonzero_demand_weeks,
        avg(weekly_demand_qty)::number(18, 4) as mean_weekly_demand,
        coalesce(stddev_samp(weekly_demand_qty), 0)::number(18, 4) as stddev_weekly_demand,
        avg(iff(weekly_demand_qty > 0, weekly_demand_qty, null))::number(18, 4) as mean_nonzero_weekly_demand,
        coalesce(stddev_samp(iff(weekly_demand_qty > 0, weekly_demand_qty, null)), 0)::number(18, 4) as stddev_nonzero_weekly_demand
    from weekly_demand
    group by 1, 2


),

ratios as (

    select
        *,
        case when mean_nonzero_weekly_demand > 0 then stddev_nonzero_weekly_demand / mean_nonzero_weekly_demand end::number(18, 4) as coefficient_of_variation,
        case when mean_nonzero_weekly_demand > 0 then power(stddev_nonzero_weekly_demand / mean_nonzero_weekly_demand, 2) end::number(18, 4) as coefficient_of_variation_squared,

        case when nonzero_demand_weeks > 0 then observed_weeks / nonzero_demand_weeks end::number(18, 4) as average_demand_interval
    from statistics

),

classified as (

    select
        *,
        case
            when nonzero_demand_weeks = 0 then 'intermittent'
            when average_demand_interval <= 1.32 and coefficient_of_variation_squared <= 0.49 then 'smooth'
            when average_demand_interval <= 1.32 and coefficient_of_variation_squared > 0.49 then 'erratic'
            when average_demand_interval > 1.32 and coefficient_of_variation_squared <= 0.49 then 'intermittent'
            else 'lumpy'
        end as demand_class
    from ratios

)

select *
from classified
