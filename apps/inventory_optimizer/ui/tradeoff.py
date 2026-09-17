"""Service-level vs inventory-investment efficient frontier."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from core.network import LocationSigma, pooling_comparison
from core.policy import allocate_service_levels, efficient_frontier, recommend_policy
from data.loader import sku_location_params
from ui.helpers import dollars, pct


def render_tradeoff(weekly: pd.DataFrame) -> None:
    st.subheader("Service level tradeoff")
    st.caption(
        "The curve is the greedy fill-rate-per-dollar frontier. Current policy is plotted "
        "as a single point — usually off the curve — so the gap is visible. No LP solver."
    )

    items = sku_location_params(weekly)
    current_recs = [recommend_policy(item) for item in items]
    current_investment = float(
        sum((max(r.current_safety_stock, 0.0) + r.current_order_qty / 2.0) * r.unit_cost for r in current_recs)
    )
    current_fr = _weighted_current_fill(items, current_recs)

    with st.spinner("Building the efficient frontier…"):
        points = efficient_frontier(items)
    frontier = pd.DataFrame(
        {
            "investment": [p.investment for p in points],
            "weighted_fill_rate": [p.weighted_fill_rate for p in points],
            "n_upgrades": [p.n_upgrades for p in points],
        }
    )

    min_inv = float(frontier["investment"].min()) if not frontier.empty else 0.0
    max_inv = float(frontier["investment"].max()) if not frontier.empty else 1.0
    ceiling = st.slider(
        "Inventory investment ceiling",
        min_value=float(min_inv),
        max_value=float(max(max_inv, current_investment)),
        value=float(min(current_investment, max_inv) if max_inv else min_inv),
        format="$%.0f",
    )
    allocated = allocate_service_levels(items, budget=ceiling)

    left, right = st.columns(2)
    left.metric("Current policy investment", dollars(current_investment))
    left.metric("Current weighted fill rate", pct(current_fr))
    right.metric("Frontier investment at ceiling", dollars(allocated.investment))
    right.metric("Frontier weighted fill rate", pct(allocated.weighted_fill_rate))

    chart = frontier.copy()
    chart["fill_rate_pct"] = chart["weighted_fill_rate"] * 100.0
    chart["series"] = "Efficient frontier"
    current_point = pd.DataFrame(
        {
            "investment": [current_investment],
            "fill_rate_pct": [current_fr * 100.0],
            "n_upgrades": [None],
            "series": ["Current policy"],
        }
    )
    st.scatter_chart(
        pd.concat([chart, current_point], ignore_index=True),
        x="investment",
        y="fill_rate_pct",
        color="series",
        height=360,
    )
    st.caption("Current policy uses the naive z·σ_d·√L safety stock seeded in the warehouse.")

    st.markdown("#### Risk pooling at equal service")
    branches = [item for item in items if item.echelon == "branch"]
    if len(branches) >= 2:
        sku_choice = st.selectbox("SKU for pooling comparison", sorted({b.sku_id for b in branches}))
        chosen = [b for b in branches if b.sku_id == sku_choice]
        recs = [recommend_policy(b) for b in chosen]
        locations = [
            LocationSigma(location_id=r.location_id, sigma_dl=r.sigma_dl, unit_cost=r.unit_cost)
            for r in recs
        ]
        pooled = pooling_comparison(locations, service_level=0.95, correlation=0.0)
        p1, p2, p3 = st.columns(3)
        p1.metric("Branch-held SS", f"{pooled.safety_stock_decentralized:,.1f}")
        p2.metric("Pooled at regional DC", f"{pooled.safety_stock_pooled:,.1f}")
        p3.metric("Inventory reduction", f"{pooled.units_reduction_pct:.0%}", dollars(pooled.dollars_reduction))
        st.caption(
            f"Square-root law ratio 1/√n = {pooled.square_root_law_ratio:.2f} for {pooled.n_locations} "
            "independent branches (Eppen 1979 / Maister 1976)."
        )
    else:
        st.write("Need at least two branch locations in the loaded data to illustrate pooling.")


def _weighted_current_fill(items, recs) -> float:
    num = 0.0
    den = 0.0
    lookup = {(r.sku_id, r.location_id): r for r in recs}
    for item in items:
        rec = lookup[(item.sku_id, item.location_id)]
        d = item.yearly_demand()
        num += rec.current_fill_rate * d
        den += d
    return float(num / den) if den else 1.0
