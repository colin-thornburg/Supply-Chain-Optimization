"""Shape a policy-recommendation set for Snowflake writeback.

This module does not open a warehouse connection. It stamps a run id and
returns a pandas DataFrame whose columns match the ``policy_recommendations``
table. The Streamlit loader (later) will CREATE TABLE IF NOT EXISTS using
:data:`POLICY_RECOMMENDATIONS_DDL` and insert these rows.

Keeping I/O out of this file lets pytest cover the contract without
Snowflake credentials.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone
from uuid import uuid4

import pandas as pd

from core.policy import PolicyRecommendation

POLICY_RECOMMENDATION_COLUMNS = (
    "run_id",
    "created_at",
    "sku",
    "location_id",
    "demand_class",
    "method",
    "target_service_level",
    "service_level_kind",
    "recommended_safety_stock",
    "recommended_reorder_point",
    "recommended_order_qty",
    "current_safety_stock",
    "current_reorder_point",
    "current_order_qty",
    "achieved_fill_rate",
    "current_fill_rate",
    "safety_stock_delta_units",
    "safety_stock_delta_dollars",
    "annual_net_benefit",
    "sigma_dl",
    "mu_dl",
    "lead_time_mean",
    "lead_time_std",
    "unit_cost",
)

POLICY_RECOMMENDATIONS_DDL = """
create table if not exists policy_recommendations (
    run_id                        varchar        not null,
    created_at                    timestamp_ntz  not null,
    sku                           varchar        not null,
    location_id                   varchar        not null,
    demand_class                  varchar,
    method                        varchar,
    target_service_level          float,
    service_level_kind            varchar,
    recommended_safety_stock      float,
    recommended_reorder_point     float,
    recommended_order_qty         float,
    current_safety_stock          float,
    current_reorder_point         float,
    current_order_qty             float,
    achieved_fill_rate            float,
    current_fill_rate             float,
    safety_stock_delta_units      float,
    safety_stock_delta_dollars    float,
    annual_net_benefit            float,
    sigma_dl                      float,
    mu_dl                         float,
    lead_time_mean                float,
    lead_time_std                 float,
    unit_cost                     float
)
""".strip()


def stamp_run(
    *,
    run_id: str | None = None,
    created_at: datetime | None = None,
) -> tuple[str, datetime]:
    """Return a (run_id, created_at) pair.

    ``run_id`` defaults to a UUID-4 hex string. ``created_at`` defaults to
    timezone-aware UTC, then is stored naive-UTC in the frame so Snowflake
    ``TIMESTAMP_NTZ`` ingestion does not double-apply a zone.
    """
    rid = run_id or uuid4().hex
    ts = created_at or datetime.now(timezone.utc)
    if ts.tzinfo is not None:
        ts = ts.astimezone(timezone.utc).replace(tzinfo=None)
    return rid, ts


def build_recommendation_frame(
    recommendations: Sequence[PolicyRecommendation],
    *,
    run_id: str | None = None,
    created_at: datetime | None = None,
) -> pd.DataFrame:
    """Tabular recommendation set, one row per SKU × location.

    Rows are sorted by ``annual_net_benefit`` descending so the
    Recommendations page can render the frame as-is. An empty input still
    returns a zero-row frame with the full column contract.
    """
    rid, ts = stamp_run(run_id=run_id, created_at=created_at)
    records = [
        {
            "run_id": rid,
            "created_at": ts,
            "sku": rec.sku_id,
            "location_id": rec.location_id,
            "demand_class": rec.demand_class,
            "method": rec.method,
            "target_service_level": rec.target_service_level,
            "service_level_kind": rec.service_level_kind,
            "recommended_safety_stock": rec.safety_stock,
            "recommended_reorder_point": rec.reorder_point,
            "recommended_order_qty": rec.order_quantity,
            "current_safety_stock": rec.current_safety_stock,
            "current_reorder_point": rec.current_reorder_point,
            "current_order_qty": rec.current_order_qty,
            "achieved_fill_rate": rec.achieved_fill_rate,
            "current_fill_rate": rec.current_fill_rate,
            "safety_stock_delta_units": rec.safety_stock_delta_units,
            "safety_stock_delta_dollars": rec.safety_stock_delta_dollars,
            "annual_net_benefit": rec.annual_net_benefit,
            "sigma_dl": rec.sigma_dl,
            "mu_dl": rec.mu_dl,
            "lead_time_mean": rec.lead_time_mean,
            "lead_time_std": rec.lead_time_std,
            "unit_cost": rec.unit_cost,
        }
        for rec in recommendations
    ]
    frame = pd.DataFrame(records, columns=list(POLICY_RECOMMENDATION_COLUMNS))
    if not frame.empty:
        frame = frame.sort_values("annual_net_benefit", ascending=False).reset_index(drop=True)
    return frame
