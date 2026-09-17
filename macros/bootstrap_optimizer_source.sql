{% macro bootstrap_optimizer_source() %}
    create table if not exists
        {{ target.database }}.{{ var('optimizer_schema', target.schema) }}.policy_recommendations (
            run_id varchar not null,
            created_at timestamp_ntz not null,
            sku varchar not null,
            location_id varchar not null,
            demand_class varchar,
            method varchar,
            target_service_level float,
            service_level_kind varchar,
            recommended_safety_stock float,
            recommended_reorder_point float,
            recommended_order_qty float,
            current_safety_stock float,
            current_reorder_point float,
            current_order_qty float,
            achieved_fill_rate float,
            current_fill_rate float,
            safety_stock_delta_units float,
            safety_stock_delta_dollars float,
            annual_net_benefit float,
            sigma_dl float,
            mu_dl float,
            lead_time_mean float,
            lead_time_std float,
            unit_cost float
        )
{% endmacro %}
