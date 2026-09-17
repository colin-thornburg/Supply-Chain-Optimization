"""Meridian Industrial Supply — multi-echelon inventory policy optimizer.

Run locally:

    streamlit run app.py -- --sample

Warehouse mode reads credentials from `.streamlit/secrets.toml` (see the
`.example` file). Never hardcode account identifiers.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import streamlit as st

from data.loader import is_sample_mode, load_supplier_scorecard, load_weekly_demand
from ui.explorer import render_explorer
from ui.helpers import PAGE_OPTIONS
from ui.overview import render_overview
from ui.recommendations import render_recommendations
from ui.scenarios import render_scenarios
from ui.tradeoff import render_tradeoff

st.set_page_config(
    page_title="Meridian Inventory Optimizer",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.title("Meridian Industrial Supply")
st.caption("Multi-echelon inventory policy optimizer on the governed dbt Semantic Layer.")

sample = is_sample_mode()
if sample:
    st.sidebar.success("Sample mode — parquet fixture, no warehouse connection.")
else:
    st.sidebar.info("Warehouse mode — Snowflake + Semantic Layer from `st.secrets`.")

page = st.sidebar.radio("Page", PAGE_OPTIONS)

with st.spinner("Loading SKU × location demand…"):
    weekly = load_weekly_demand(sample=sample)
    scorecard = load_supplier_scorecard(sample=sample)

st.sidebar.metric("SKU × location weeks", f"{len(weekly):,}")
st.sidebar.metric("Suppliers", f"{scorecard['supplier_id'].nunique():,}")
st.sidebar.caption("Math lives in `core/`. KPIs on Network overview come from the Semantic Layer.")

if page == "Network overview":
    render_overview(sample)
elif page == "Policy explorer":
    render_explorer(weekly)
elif page == "Service level tradeoff":
    render_tradeoff(weekly)
elif page == "Scenario planner":
    render_scenarios(weekly)
else:
    render_recommendations(weekly, sample)
