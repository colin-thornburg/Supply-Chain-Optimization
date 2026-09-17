"""Risk pooling and echelon rollup tests. No warehouse required."""

from __future__ import annotations

import math

import pytest

from core.network import (
    LocationSigma,
    echelon_demand_rollup,
    pooling_comparison,
    sigma_pooled_independent,
    square_root_law_ratio,
)
from core.policy import z_from_service_level


def test_square_root_law_four_identical_locations():
    assert square_root_law_ratio(4) == pytest.approx(0.5)
    assert square_root_law_ratio(1) == pytest.approx(1.0)
    assert square_root_law_ratio(9) == pytest.approx(1.0 / 3.0)


def test_square_root_law_rejects_non_positive():
    with pytest.raises(ValueError):
        square_root_law_ratio(0)


def test_pooled_sigma_independent_identical():
    sigmas = [10.0, 10.0, 10.0, 10.0]
    assert sigma_pooled_independent(sigmas) == pytest.approx(20.0)


def test_pooling_four_identical_branches_halves_safety_stock():
    z = z_from_service_level(0.95)
    locations = [
        LocationSigma(location_id=f"BR-{i}", sigma_dl=8.0, unit_cost=12.0)
        for i in range(4)
    ]
    result = pooling_comparison(locations, service_level=0.95, correlation=0.0)
    assert result.n_locations == 4
    assert result.safety_stock_decentralized == pytest.approx(z * 32.0)
    assert result.safety_stock_pooled == pytest.approx(z * 16.0)
    assert result.units_reduction_pct == pytest.approx(0.5)
    assert result.square_root_law_ratio == pytest.approx(0.5)
    assert result.dollars_reduction > 0.0


def test_pooling_single_location_no_benefit():
    locations = [LocationSigma(location_id="BR-1", sigma_dl=5.0, unit_cost=10.0)]
    result = pooling_comparison(locations, 0.95)
    assert result.units_reduction == pytest.approx(0.0)
    assert result.safety_stock_pooled == pytest.approx(result.safety_stock_decentralized)


def test_pooling_zero_variance():
    locations = [
        LocationSigma(location_id="BR-1", sigma_dl=0.0, unit_cost=10.0),
        LocationSigma(location_id="BR-2", sigma_dl=0.0, unit_cost=10.0),
    ]
    result = pooling_comparison(locations, 0.99)
    assert result.safety_stock_decentralized == pytest.approx(0.0)
    assert result.safety_stock_pooled == pytest.approx(0.0)
    assert result.units_reduction == pytest.approx(0.0)
    assert result.dollars_reduction == pytest.approx(0.0)


def test_perfect_correlation_kills_pooling_benefit():
    locations = [
        LocationSigma(location_id="BR-1", sigma_dl=6.0, unit_cost=8.0),
        LocationSigma(location_id="BR-2", sigma_dl=6.0, unit_cost=8.0),
    ]
    independent = pooling_comparison(locations, 0.95, correlation=0.0)
    perfect = pooling_comparison(locations, 0.95, correlation=1.0)
    assert perfect.units_reduction == pytest.approx(0.0)
    assert independent.units_reduction > perfect.units_reduction


def test_echelon_rollup_independent_sum_of_variances():
    mean, std = echelon_demand_rollup([10.0, 20.0], [4.0, 9.0], independent=True)
    assert mean == pytest.approx(30.0)
    assert std == pytest.approx(math.sqrt(13.0))


def test_echelon_rollup_empty():
    mean, std = echelon_demand_rollup([], [])
    assert mean == 0.0
    assert std == 0.0
