"""Scenario planner — supplier, region, and demand shocks."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.scenarios import Shock, compare_policies_under_shock
from data.loader import sku_location_params
from ui.helpers import cached_recommendations, pct


def render_scenarios(weekly: pd.DataFrame) -> None:
    st.subheader("Scenario planner")
    st.caption(
        "Each shock is a comparative static: we hold today's (ROP, Q) fixed against the "
        "new lead-time-demand distribution. Recommended policy is usually more robust "
        "because it already priced lead-time variance. Re-optimize is the ceiling."
    )

    items = sku_location_params(weekly)
    recs = cached_recommendations(items, 0.95)
    suppliers = sorted({item.supplier_id for item in items if item.supplier_id})
    regions = sorted({item.sourcing_region for item in items if item.sourcing_region})
    categories = sorted({item.category for item in items if item.category})

    kind = st.radio(
        "Shock",
        ("Supplier lead time doubles", "Sourcing region disrupted", "Category demand +20%"),
        horizontal=True,
    )
    if kind == "Supplier lead time doubles":
        key = st.selectbox("Supplier", suppliers)
        shock = Shock(kind="lead_time", key=key, multiplier=2.0)
    elif kind == "Sourcing region disrupted":
        key = st.selectbox("Sourcing region", regions)
        shock = Shock(kind="region", key=key, multiplier=2.0)
    else:
        key = st.selectbox("Category", categories)
        shock = Shock(kind="demand", key=key, multiplier=1.2)

    comparison = compare_policies_under_shock(items, shock, recommendations=recs)

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("SKUs shocked", f"{comparison.n_shocked} / {comparison.n_items}")
    c2.metric("Current policy after shock", pct(comparison.current_fill_rate_shocked), delta=pct(comparison.current_fill_rate_shocked - comparison.current_fill_rate_baseline))
    c3.metric("Recommended policy after shock", pct(comparison.recommended_fill_rate_shocked), delta=pct(comparison.recommended_fill_rate_shocked - comparison.recommended_fill_rate_baseline))
    c4.metric("Re-optimized after shock", pct(comparison.reoptimized_fill_rate))

    st.info(shock.describe())

    rows = pd.DataFrame(
        [
            {
                "sku": row.sku_id,
                "location": row.location_id,
                "class": row.demand_class,
                "method": row.method,
                "shocked": row.shocked,
                "current_baseline_fr": row.baseline_fill_rate_current,
                "current_shocked_fr": row.shocked_fill_rate_current,
                "recommended_shocked_fr": row.shocked_fill_rate_recommended,
                "reoptimized_fr": row.reoptimized_fill_rate,
            }
            for row in comparison.rows
            if row.shocked
        ]
    )
    if rows.empty:
        st.write("That shock did not match any loaded SKU × location.")
        return
    st.dataframe(
        rows.sort_values("current_shocked_fr"),
        width="stretch",
        hide_index=True,
    )
