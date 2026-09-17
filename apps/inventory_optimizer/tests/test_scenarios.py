"""Scenario shock tests. No warehouse required."""

from __future__ import annotations

import pytest

from core.policy import SkuLocationParams, recommend_policy
from core.scenarios import Shock, apply_shock, compare_policies_under_shock


def _item(**kwargs) -> SkuLocationParams:
    defaults = dict(
        sku_id="SKU-SEAL-014",
        location_id="BR-CHI",
        demand_mean=8.0,
        demand_std=2.0,
        demand_class="smooth",
        lead_time_mean=3.0,
        lead_time_std=1.0,
        unit_cost=18.0,
        target_service_level=0.95,
        supplier_id="SUP-MIDWEST-04",
        sourcing_region="midwest_mill",
        category="seals",
        current_safety_stock=6.0,
        current_reorder_point=30.0,
        current_order_qty=40.0,
    )
    defaults.update(kwargs)
    return SkuLocationParams(**defaults)


def test_supplier_lead_time_shock_scales_mean_and_std():
    item = _item()
    shocked = apply_shock(item, Shock(kind="lead_time", key="SUP-MIDWEST-04", multiplier=2.0))
    assert shocked.lead_time_mean == pytest.approx(6.0)
    assert shocked.lead_time_std == pytest.approx(2.0)
    assert shocked.demand_mean == item.demand_mean


def test_unmatched_supplier_is_unchanged():
    item = _item()
    shocked = apply_shock(item, Shock(kind="lead_time", key="SUP-OTHER", multiplier=2.0))
    assert shocked is item


def test_region_shock_hits_sourcing_region():
    item = _item()
    shocked = apply_shock(item, Shock(kind="region", key="midwest_mill", multiplier=3.0))
    assert shocked.lead_time_mean == pytest.approx(9.0)


def test_demand_step_up_preserves_cv():
    item = _item()
    shocked = apply_shock(item, Shock(kind="demand", key="seals", multiplier=1.2))
    assert shocked.demand_mean == pytest.approx(9.6)
    assert shocked.demand_std == pytest.approx(2.4)
    assert shocked.demand_std / shocked.demand_mean == pytest.approx(
        item.demand_std / item.demand_mean
    )


def test_unknown_shock_kind_raises():
    with pytest.raises(ValueError, match="unknown shock kind"):
        apply_shock(_item(), Shock(kind="price", key="x"))


def test_current_policy_loses_more_service_than_recommended_when_lt_doubles():
    item = _item()
    rec = recommend_policy(item)
    comparison = compare_policies_under_shock(
        [item],
        Shock(kind="lead_time", key="SUP-MIDWEST-04", multiplier=2.0),
        recommendations=[rec],
    )
    assert comparison.n_shocked == 1
    # Holding today's ROP against a doubled lead time should hurt.
    assert comparison.current_fill_rate_shocked < comparison.current_fill_rate_baseline
    # Re-optimizing after the shock recovers service versus the frozen current policy.
    assert comparison.reoptimized_fill_rate > comparison.current_fill_rate_shocked
    row = comparison.rows[0]
    assert row.shocked is True
    assert row.fill_rate_gap_current < 0.0
