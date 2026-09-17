"""Ranked policy changes, CSV export, and Snowflake writeback."""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st

from core.writeback import POLICY_RECOMMENDATIONS_DDL, build_recommendation_frame
from data.loader import is_sample_mode, sku_location_params, write_recommendations_to_snowflake
from ui.helpers import cached_recommendations, recommendation_table


def render_recommendations(weekly, sample: bool) -> None:
    st.subheader("Recommendations")
    st.caption(
        "Ranked by annual dollar impact (holding cost versus shortage penalty). "
        "Writeback stamps a run id and UTC timestamp onto `policy_recommendations`."
    )

    items = sku_location_params(weekly)
    recs = cached_recommendations(items, 0.95)
    table = recommendation_table(recs)
    st.dataframe(table, width="stretch", hide_index=True)

    csv = table.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Export CSV",
        data=csv,
        file_name="meridian_policy_recommendations.csv",
        mime="text/csv",
    )

    if st.button("Write recommendation set to Snowflake"):
        frame = build_recommendation_frame(recs, created_at=datetime.now(timezone.utc))
        if sample or is_sample_mode():
            st.warning(
                "Sample mode does not write to Snowflake. Disable `--sample` and add "
                "credentials in `.streamlit/secrets.toml` to push `policy_recommendations`."
            )
            st.dataframe(frame.head(20), width="stretch", hide_index=True)
            return
        try:
            n = write_recommendations_to_snowflake(frame, POLICY_RECOMMENDATIONS_DDL)
            st.success(f"Wrote {n} rows to policy_recommendations (run_id={frame['run_id'].iloc[0]}).")
        except Exception as exc:
            st.error(f"Writeback failed: {exc}")
