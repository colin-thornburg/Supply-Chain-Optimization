"""Safety stock, EOQ rounding, fill-rate routing. No warehouse required."""

from __future__ import annotations

import math

import pytest

from core.policy import (
    SkuLocationParams,
    achieved_fill_rate,
    allocate_service_levels,
    economic_order_quantity,
    efficient_frontier,
    recommend_policy,
    reorder_point,
    round_order_quantity,
    safety_stock_normal,
    sigma_demand_over_lead_time,
    z_from_service_level,
)


def _smooth_item(**kwargs) -> SkuLocationParams:
    defaults = dict(
        sku_id="SKU-BEARING-001",
        location_id="BR-ATL",
        demand_mean=10.0,
        demand_std=2.0,
        demand_class="smooth",
        lead_time_mean=4.0,
        lead_time_std=0.5,
        unit_cost=25.0,
        target_service_level=0.95,
        min_order_qty=1.0,
        order_multiple=1.0,
        order_cost=50.0,
        holding_rate=0.25,
        current_safety_stock=8.0,
        current_reorder_point=40.0,
        current_order_qty=50.0,
    )
    defaults.update(kwargs)
    return SkuLocationParams(**defaults)


def test_sigma_dl_includes_lead_time_variance():
    # Silver/Pyke/Hopp-Spearman: sqrt(L * s_d^2 + d^2 * s_L^2)
    sigma = sigma_demand_over_lead_time(
        demand_mean=10.0,
        demand_std=2.0,
        lead_time_mean=4.0,
        lead_time_std=2.0,
    )
    assert sigma == pytest.approx(math.sqrt(4 * 4 + 100 * 4))


def test_lead_time_variance_dominates_naive_form():
    """Demo moment: unreliable suppliers make z * s_d * sqrt(L) badly low."""
    d_bar, sigma_d, lead_time, sigma_l = 10.0, 2.0, 4.0, 2.0
    sigma_dl = sigma_demand_over_lead_time(d_bar, sigma_d, lead_time, sigma_l)
    naive = sigma_d * math.sqrt(lead_time)
    assert sigma_dl > 4 * naive
    z = z_from_service_level(0.95)
    full_ss = z * sigma_dl
    naive_ss = z * naive
    assert full_ss > 4 * naive_ss


def test_safety_stock_normal_is_z_times_sigma_dl():
    z = z_from_service_level(0.95)
    ss = safety_stock_normal(10.0, 2.0, 4.0, 0.5, 0.95)
    sigma = sigma_demand_over_lead_time(10.0, 2.0, 4.0, 0.5)
    assert ss == pytest.approx(z * sigma)
    assert ss == pytest.approx(reorder_point(10.0, 4.0, ss) - 40.0)


def test_zero_variance_safety_stock_is_zero():
    ss = safety_stock_normal(
        demand_mean=10.0,
        demand_std=0.0,
        lead_time_mean=4.0,
        lead_time_std=0.0,
        service_level=0.99,
    )
    assert ss == pytest.approx(0.0)
    assert sigma_demand_over_lead_time(10.0, 0.0, 4.0, 0.0) == pytest.approx(0.0)


def test_zero_demand_safety_stock_is_zero():
    ss = safety_stock_normal(0.0, 0.0, 4.0, 1.0, 0.95)
    # mu_DL = 0, sigma_DL = 0 * sigma_L = 0
    assert ss == pytest.approx(0.0)
    rec = recommend_policy(
        _smooth_item(
            demand_mean=0.0,
            demand_std=0.0,
            demand_class="intermittent",
            current_safety_stock=0.0,
            current_reorder_point=0.0,
        )
    )
    assert rec.safety_stock == pytest.approx(0.0)
    assert rec.reorder_point == pytest.approx(0.0)
    assert rec.order_quantity == pytest.approx(0.0)


def test_lead_time_zero_and_zero_lt_variance():
    sigma = sigma_demand_over_lead_time(10.0, 3.0, 0.0, 0.0)
    assert sigma == pytest.approx(0.0)
    ss = safety_stock_normal(10.0, 3.0, 0.0, 0.0, 0.95)
    assert ss == pytest.approx(0.0)
    assert reorder_point(10.0, 0.0, ss) == pytest.approx(0.0)


def test_lead_time_zero_with_positive_lt_std_uses_second_term():
    sigma = sigma_demand_over_lead_time(10.0, 3.0, 0.0, 2.0)
    assert sigma == pytest.approx(20.0)  # d_bar * sigma_L


def test_single_observation_item_has_zero_demand_std():
    rec = recommend_policy(
        _smooth_item(demand_mean=12.0, demand_std=0.0, lead_time_std=0.0)
    )
    assert rec.sigma_dl == pytest.approx(0.0)
    assert rec.safety_stock == pytest.approx(0.0)
    assert rec.reorder_point == pytest.approx(12.0 * 4.0)


def test_eoq_harris_wilson_formula():
    # D=520, S=50, H=2.5 → sqrt(2*520*50/2.5) = sqrt(20800) ≈ 144.222
    eoq = economic_order_quantity(520.0, 50.0, 2.5)
    assert eoq == pytest.approx(math.sqrt(2 * 520 * 50 / 2.5))


def test_eoq_zero_demand_is_zero():
    assert economic_order_quantity(0.0, 50.0, 2.5) == 0.0


def test_eoq_zero_holding_returns_annual_demand():
    assert economic_order_quantity(520.0, 50.0, 0.0) == pytest.approx(520.0)


def test_round_order_quantity_multiple():
    assert round_order_quantity(144.2, min_order_qty=1.0, order_multiple=10.0) == 150.0


def test_round_order_quantity_moq_binds():
    assert round_order_quantity(144.2, min_order_qty=200.0, order_multiple=1.0) == 200.0


def test_round_order_quantity_moq_and_multiple():
    # max(144.2, 200) = 200; ceil(200/60)*60 = 240
    assert round_order_quantity(144.2, min_order_qty=200.0, order_multiple=60.0) == 240.0


def test_round_order_quantity_zero_eoq_zero_moq():
    assert round_order_quantity(0.0, min_order_qty=0.0, order_multiple=12.0) == 0.0


def test_round_order_quantity_already_on_multiple():
    assert round_order_quantity(120.0, min_order_qty=1.0, order_multiple=12.0) == 120.0


def test_recommend_policy_smooth_uses_normal_csl():
    rec = recommend_policy(_smooth_item())
    assert rec.method == "normal_csl"
    assert rec.service_level_kind == "cycle_service_level"
    assert rec.z == pytest.approx(z_from_service_level(0.95))
    assert rec.safety_stock == pytest.approx(
        safety_stock_normal(10.0, 2.0, 4.0, 0.5, 0.95)
    )
    assert rec.reorder_point == pytest.approx(40.0 + rec.safety_stock)


def test_recommend_policy_service_override_recomputes():
    low = recommend_policy(_smooth_item(), target_service_level=0.80)
    high = recommend_policy(_smooth_item(), target_service_level=0.99)
    assert high.safety_stock > low.safety_stock
    assert high.achieved_csl > low.achieved_csl


def test_intermittent_routes_to_poisson_when_not_overdispersed():
    # Low weekly variance, high ADI class, short reliable lead time so
    # sigma_DL^2 ≈ L * sigma_d^2 is not much larger than mu_DL.
    item = _smooth_item(
        demand_mean=0.5,
        demand_std=0.5,
        demand_class="intermittent",
        lead_time_mean=1.0,
        lead_time_std=0.0,
        current_safety_stock=0.0,
        current_reorder_point=0.0,
        current_order_qty=10.0,
        min_order_qty=10.0,
        order_multiple=10.0,
    )
    rec = recommend_policy(item)
    assert rec.method == "poisson_fill_rate"
    assert rec.service_level_kind == "fill_rate"
    assert rec.reorder_point >= 0.0
    assert 0.0 <= rec.achieved_fill_rate <= 1.0


def test_lumpy_routes_to_negbin_when_overdispersed():
    item = _smooth_item(
        demand_mean=2.0,
        demand_std=6.0,
        demand_class="lumpy",
        lead_time_mean=3.0,
        lead_time_std=1.5,
        current_safety_stock=5.0,
        current_reorder_point=11.0,
        current_order_qty=20.0,
    )
    rec = recommend_policy(item)
    assert rec.method == "negbin_fill_rate"
    assert rec.overdispersion > 1.0
    assert rec.achieved_fill_rate >= rec.target_service_level - 0.02


def test_fill_rate_improves_with_higher_rop():
    item = _smooth_item()
    low = achieved_fill_rate(item, reorder_point_units=30.0, order_qty=50.0, method="normal_csl")
    high = achieved_fill_rate(item, reorder_point_units=80.0, order_qty=50.0, method="normal_csl")
    assert high > low
    assert high <= 1.0


def test_frontier_is_monotone_in_investment_and_fill_rate():
    items = [
        _smooth_item(sku_id="A", location_id="BR-1", unit_cost=10.0),
        _smooth_item(sku_id="B", location_id="BR-2", demand_mean=30.0, unit_cost=5.0),
    ]
    points = efficient_frontier(items)
    assert len(points) >= 2
    for prev, nxt in zip(points, points[1:]):
        assert nxt.investment >= prev.investment - 1e-6
        assert nxt.weighted_fill_rate >= prev.weighted_fill_rate - 1e-6


def test_budget_constraint_caps_investment():
    items = [
        _smooth_item(sku_id="A", location_id="BR-1"),
        _smooth_item(sku_id="B", location_id="BR-2", demand_mean=20.0, unit_cost=40.0),
    ]
    full = allocate_service_levels(items, budget=1e12)
    tight = allocate_service_levels(items, budget=full.investment * 0.4)
    assert tight.investment <= full.investment + 1e-6
    assert tight.weighted_fill_rate <= full.weighted_fill_rate + 1e-6
