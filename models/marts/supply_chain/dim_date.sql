with dates as (

    select distinct demand_date as date_day
    from {{ ref('int_demand_daily_spine') }}

)

select
    date_day,
    to_number(to_char(date_day, 'YYYYMMDD')) as date_key,
    year(date_day) as calendar_year,
    quarter(date_day) as calendar_quarter,
    month(date_day) as calendar_month,
    monthname(date_day) as month_name,
    weekiso(date_day) as calendar_week,
    dayofweekiso(date_day) as day_of_week,
    dayname(date_day) as day_name,
    date_trunc('week', date_day)::date as week_start_date,
    date_trunc('month', date_day)::date as month_start_date,
    dayofweekiso(date_day) in (6, 7) as is_weekend
from dates
