with locations as (

    select *
    from {{ ref('stg_wms__locations') }}

),

hierarchy as (

    select
        child.location_id,
        child.location_name,
        child.location_type,
        child.parent_location_id,
        child.state,
        child.region,
        child.square_feet,
        child.is_active,
        child.opened_date,
        case child.location_type
            when 'national_dc' then 0
            when 'regional_dc' then 1
            when 'branch' then 2
            when 'onsite' then 3
        end as echelon_level,
        case child.location_type
            when 'national_dc' then child.location_id
            when 'regional_dc' then parent_1.location_id
            when 'branch' then parent_2.location_id
            when 'onsite' then parent_3.location_id
        end as national_dc_location_id,
        case child.location_type
            when 'national_dc' then child.location_name
            when 'regional_dc' then parent_1.location_name || ' > ' || child.location_name
            when 'branch' then parent_2.location_name || ' > ' || parent_1.location_name || ' > ' || child.location_name
            when 'onsite' then parent_3.location_name || ' > ' || parent_2.location_name || ' > ' || parent_1.location_name || ' > ' || child.location_name
        end as echelon_path
    from locations as child
    left join locations as parent_1 on child.parent_location_id = parent_1.location_id
    left join locations as parent_2 on parent_1.parent_location_id = parent_2.location_id
    left join locations as parent_3 on parent_2.parent_location_id = parent_3.location_id

)

select *
from hierarchy
