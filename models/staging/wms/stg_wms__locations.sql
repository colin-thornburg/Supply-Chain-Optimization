with source_data as (

    select *
    from {{ source('wms', 'locations') }}

),

casted as (

    select
        trim(location_id)::varchar as location_id,
        trim(location_name)::varchar as location_name,
        trim(location_type)::varchar as location_type,
        nullif(trim(parent_location_id), '')::varchar as parent_location_id,
        trim(state)::varchar as state,
        trim(region)::varchar as region,
        square_feet::number(18, 0) as square_feet,
        is_active::boolean as is_active,
        opened_date::date as opened_date
    from source_data

)

select *
from casted
