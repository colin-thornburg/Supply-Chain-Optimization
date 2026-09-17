"""Network overview — Semantic Layer KPIs, not re-aggregated mart math."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from data.loader import query_semantic_layer
from ui.helpers import METRIC_CAPTIONS, dollars, pct


def render_overview(sample: bool) -> None:
    st.subheader("Network overview")
    st.caption(
        "Headline figures are queried from the dbt Semantic Layer so they match "
        "governed metric definitions. Optimizer math never reimplements these KPIs."
    )

    kpis = query_semantic_layer(("on_hand_value",), sample=sample, sample_name="headline_kpis")
    kpi_map = {row["metric"]: row["value"] for _, row in kpis.iterrows()}
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("On-hand inventory", dollars(kpi_map.get("on_hand_value") or 0))
    c1.caption(METRIC_CAPTIONS["on_hand_value"])
    c2.metric("Line fill rate", pct(kpi_map.get("line_fill_rate") or 0))
    c2.caption(METRIC_CAPTIONS["line_fill_rate"])
    c3.metric("Unit fill rate", pct(kpi_map.get("unit_fill_rate") or 0))
    c3.caption(METRIC_CAPTIONS["unit_fill_rate"])
    c4.metric("Demand during stockouts", f"{kpi_map.get('stockout_impact_units') or 0:,.0f} units")
    c4.caption(METRIC_CAPTIONS["stockout_impact_units"])

    st.markdown("#### Inventory value by echelon and ABC class")
    inventory = query_semantic_layer(
        ("on_hand_value", "on_order_value", "excess_obsolete_on_hand_value"),
        ("location__location_type", "sku__abc_class"),
        sample=sample,
        sample_name="inventory_by_echelon_abc",
    )
    inventory = _normalize_inventory(inventory)
    st.caption(
        f"{METRIC_CAPTIONS['on_hand_value']} Grouped by `location__location_type` and `sku__abc_class` "
        "(saved query `inventory_value_by_echelon_and_abc_class`)."
    )
    if not inventory.empty:
        pivot = inventory.pivot_table(
            index="location_type",
            columns="abc_class",
            values="on_hand_value",
            aggfunc="sum",
        ).fillna(0)
        st.bar_chart(pivot)
        st.dataframe(inventory, width="stretch", hide_index=True)

    left, right = st.columns(2)
    with left:
        st.markdown("#### Fill rate trend")
        trend = query_semantic_layer(
            ("weekly_line_fill_rate",),
            ("metric_time__month",),
            sample=sample,
            sample_name="fill_rate_trend",
        )
        trend = _normalize_trend(trend)
        st.caption(METRIC_CAPTIONS["weekly_line_fill_rate"])
        if not trend.empty:
            st.line_chart(trend, x="month", y="weekly_line_fill_rate")
    with right:
        st.markdown("#### Top stockout-impact SKUs")
        stockouts = query_semantic_layer(
            ("stockout_days", "stockout_impact_units"),
            ("sku__sku",),
            sample=sample,
            sample_name="top_stockout_impact",
        )
        st.caption(
            f"{METRIC_CAPTIONS['stockout_impact_units']} Ranked SKUs from saved query "
            "`top_stockout_impact_skus`."
        )
        if not stockouts.empty:
            show = stockouts.copy()
            if "sku" not in show.columns and "sku__sku" in show.columns:
                show = show.rename(columns={"sku__sku": "sku"})
            st.dataframe(show, width="stretch", hide_index=True)


def _normalize_inventory(frame: pd.DataFrame) -> pd.DataFrame:
    rename = {
        "location__location_type": "location_type",
        "sku__abc_class": "abc_class",
    }
    out = frame.rename(columns=rename)
    if "on_hand_value" not in out.columns and not out.empty:
        # sample fixture already uses on_hand_value
        pass
    return out


def _normalize_trend(frame: pd.DataFrame) -> pd.DataFrame:
    out = frame.copy()
    if "month" not in out.columns:
        for col in ("metric_time__month", "metric_time"):
            if col in out.columns:
                out = out.rename(columns={col: "month"})
                break
    if "month" in out.columns:
        out["month"] = pd.to_datetime(out["month"])
    return out
