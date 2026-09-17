"""Policy explorer — one SKU × location, current vs recommended."""

from __future__ import annotations

import numpy as np
import pandas as pd
import streamlit as st
from scipy import stats

from core.demand import demand_statistics
from core.policy import recommend_policy, sigma_demand_over_lead_time
from data.loader import sku_location_params
from ui.helpers import dollars, pct


def render_explorer(weekly: pd.DataFrame) -> None:
    st.subheader("Policy explorer")
    st.caption(
        "Override the target service level to recompute safety stock. Smooth and erratic "
        "SKUs use Type-I CSL with demand *and* lead-time variance. Intermittent and lumpy "
        "SKUs use a Poisson or negative-binomial fill-rate model — the method is flagged below."
    )

    skus = sorted(weekly["sku"].unique())
    sku = st.selectbox("SKU", skus)
    loc_options = sorted(weekly.loc[weekly["sku"] == sku, "location_id"].unique())
    location_id = st.selectbox("Location", loc_options)
    target = st.slider("Target service level", 0.80, 0.995, 0.95, 0.005)

    history = weekly[(weekly["sku"] == sku) & (weekly["location_id"] == location_id)].sort_values("demand_week")
    if history.empty:
        st.warning("No weekly history for that SKU × location.")
        return

    item = sku_location_params(history)[0]
    rec = recommend_policy(item, target_service_level=target)
    stats_bundle = demand_statistics(history["gross_demand_qty"].to_numpy())
    latest = history.iloc[-1]

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Demand class", rec.demand_class)
    m2.metric("Method applied", rec.method.replace("_", " "))
    m3.metric("Current fill rate", pct(rec.current_fill_rate))
    m4.metric("Recommended fill rate", pct(rec.achieved_fill_rate), delta=pct(rec.fill_rate_delta))

    a, b, c = st.columns(3)
    a.metric("Safety stock", f"{rec.safety_stock:,.1f}", delta=f"{rec.safety_stock_delta_units:,.1f} units")
    b.metric("Reorder point", f"{rec.reorder_point:,.1f}", delta=f"{rec.reorder_point - rec.current_reorder_point:,.1f}")
    c.metric("SS investment delta", dollars(rec.safety_stock_delta_dollars))

    naive = rec.z * item.demand_std * np.sqrt(item.lead_time_mean) if rec.z is not None else None
    sigma_dl = sigma_demand_over_lead_time(
        item.demand_mean, item.demand_std, item.lead_time_mean, item.lead_time_std
    )
    if naive is not None and item.lead_time_std > 0:
        st.info(
            f"Combined σ_DL = {sigma_dl:.2f}. The naive z·σ_d·√L form would hold only "
            f"{naive:.1f} units of safety stock versus {rec.safety_stock:.1f} once lead-time "
            f"variance is included. Lead time for {item.supplier_id}: "
            f"{item.lead_time_mean * 7:.1f} ± {item.lead_time_std * 7:.1f} days."
        )

    st.markdown("#### Weekly demand and fitted lead-time-demand distribution")
    st.line_chart(history.set_index("demand_week")["gross_demand_qty"], height=220)

    mu = rec.mu_dl
    grid = np.linspace(max(mu - 4 * max(sigma_dl, 1.0), 0.0), mu + 4 * max(sigma_dl, 1.0) + 1, 80)
    if rec.method == "normal_csl" and sigma_dl > 0:
        density = stats.norm.pdf(grid, loc=mu, scale=sigma_dl)
        st.area_chart(pd.DataFrame({"lead_time_demand": grid, "density": density}).set_index("lead_time_demand"))
        st.caption("Fitted normal lead-time demand used for Type-I safety stock.")
    else:
        st.caption(
            f"{rec.demand_class.title()} demand uses {rec.method.replace('_', ' ')}. "
            f"ADI={stats_bundle.adi:.2f}, CV²(size)={stats_bundle.cv2_size:.2f}."
        )
        st.bar_chart(history["gross_demand_qty"].value_counts().sort_index())

    st.markdown("#### Current vs recommended")
    compare = pd.DataFrame(
        {
            "policy": ["Current (naive)", "Recommended"],
            "safety_stock": [rec.current_safety_stock, rec.safety_stock],
            "reorder_point": [rec.current_reorder_point, rec.reorder_point],
            "order_qty": [rec.current_order_qty, rec.order_quantity],
            "fill_rate": [rec.current_fill_rate, rec.achieved_fill_rate],
            "csl": [rec.current_csl, rec.achieved_csl],
        }
    )
    st.dataframe(compare, width="stretch", hide_index=True)
    st.caption(
        f"{latest.get('product_name', sku)} at {latest.get('location_name', location_id)}. "
        f"Annual net benefit of the recommendation: {dollars(rec.annual_net_benefit)} "
        "(holding cost vs shortage penalty at 1× unit cost)."
    )
