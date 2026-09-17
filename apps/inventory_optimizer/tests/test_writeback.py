"""Writeback frame contract tests. No warehouse required."""

from __future__ import annotations

from datetime import datetime, timezone

from core.policy import SkuLocationParams, recommend_policy
from core.writeback import (
    POLICY_RECOMMENDATION_COLUMNS,
    POLICY_RECOMMENDATIONS_DDL,
    build_recommendation_frame,
    stamp_run,
)


def test_empty_frame_still_has_contract_columns():
    frame = build_recommendation_frame([])
    assert list(frame.columns) == list(POLICY_RECOMMENDATION_COLUMNS)
    assert frame.empty


def test_frame_is_stamped_and_sorted_by_benefit():
    low = recommend_policy(
        SkuLocationParams(
            sku_id="LOW",
            location_id="BR-1",
            demand_mean=5.0,
            demand_std=1.0,
            demand_class="smooth",
            lead_time_mean=2.0,
            lead_time_std=0.1,
            unit_cost=4.0,
            current_safety_stock=20.0,
            current_reorder_point=30.0,
            current_order_qty=10.0,
        )
    )
    high = recommend_policy(
        SkuLocationParams(
            sku_id="HIGH",
            location_id="BR-2",
            demand_mean=40.0,
            demand_std=5.0,
            demand_class="smooth",
            lead_time_mean=4.0,
            lead_time_std=2.0,
            unit_cost=50.0,
            current_safety_stock=0.0,
            current_reorder_point=160.0,
            current_order_qty=80.0,
        )
    )
    ts = datetime(2026, 9, 17, 16, 0, tzinfo=timezone.utc)
    frame = build_recommendation_frame([low, high], run_id="run-demo-1", created_at=ts)
    assert (frame["run_id"] == "run-demo-1").all()
    assert frame["created_at"].nunique() == 1
    assert list(frame["sku"]) == list(
        frame.sort_values("annual_net_benefit", ascending=False)["sku"]
    )
    assert "create table if not exists policy_recommendations" in POLICY_RECOMMENDATIONS_DDL


def test_stamp_run_strips_timezone_for_ntz():
    rid, ts = stamp_run(
        run_id="abc", created_at=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    )
    assert rid == "abc"
    assert ts.tzinfo is None
    assert ts.hour == 12
