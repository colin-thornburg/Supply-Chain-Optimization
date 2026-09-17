"""Shared Streamlit helpers."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.policy import PolicyRecommendation, SkuLocationParams, recommend_policy


PAGE_OPTIONS = (
    "Network overview",
    "Policy explorer",
    "Service level tradeoff",
    "Scenario planner",
    "Recommendations",
)

METRIC_CAPTIONS = {
    "on_hand_value": "Semantic Layer metric: `on_hand_value` (period-end, latest snapshot — not summed through time).",
    "line_fill_rate": "Semantic Layer metric: `line_fill_rate`.",
    "unit_fill_rate": "Semantic Layer metric: `unit_fill_rate`.",
    "weekly_line_fill_rate": "Semantic Layer metric: `weekly_line_fill_rate`.",
    "stockout_impact_units": "Semantic Layer metric: `stockout_impact_units`.",
    "stockout_days": "Semantic Layer metric: `stockout_days`.",
    "supplier_on_time_rate": "Semantic Layer metric: `supplier_on_time_rate`.",
    "gross_demand_units": "Semantic Layer metric: `gross_demand_units`.",
    "on_order_value": "Semantic Layer metric: `on_order_value`.",
    "excess_obsolete_on_hand_value": "Semantic Layer metric: `excess_obsolete_on_hand_value`.",
}


def dollars(value: float) -> str:
    return f"${value:,.0f}"


def pct(value: float) -> str:
    return f"{value:.1%}"


def cached_recommendations(
    items: list[SkuLocationParams],
    target_service_level: float,
) -> list[PolicyRecommendation]:
    key = (
        "recs",
        round(target_service_level, 4),
        tuple((i.sku_id, i.location_id, i.demand_mean, i.lead_time_mean) for i in items),
    )
    if st.session_state.get("_rec_key") != key:
        st.session_state["_rec_key"] = key
        st.session_state["_recs"] = [
            recommend_policy(item, target_service_level=target_service_level) for item in items
        ]
    return st.session_state["_recs"]


def recommendation_table(recs: list[PolicyRecommendation]) -> pd.DataFrame:
    rows = [
        {
            "sku": rec.sku_id,
            "location": rec.location_id,
            "demand_class": rec.demand_class,
            "method": rec.method,
            "current_ss": rec.current_safety_stock,
            "recommended_ss": rec.safety_stock,
            "current_rop": rec.current_reorder_point,
            "recommended_rop": rec.reorder_point,
            "order_qty": rec.order_quantity,
            "current_fill_rate": rec.current_fill_rate,
            "recommended_fill_rate": rec.achieved_fill_rate,
            "ss_delta_$": rec.safety_stock_delta_dollars,
            "annual_net_benefit": rec.annual_net_benefit,
        }
        for rec in recs
    ]
    frame = pd.DataFrame(rows)
    if not frame.empty:
        frame = frame.sort_values("annual_net_benefit", ascending=False).reset_index(drop=True)
    return frame
