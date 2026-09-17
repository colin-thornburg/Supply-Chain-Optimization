"""Demand classification tests. No warehouse required."""

from __future__ import annotations

import math

import numpy as np
import pytest

from core.demand import (
    ADI_CUTOFF,
    CV2_CUTOFF,
    average_demand_interval,
    classify_demand,
    coefficient_of_variation,
    cv_squared_demand_size,
    demand_mean,
    demand_statistics,
    demand_std,
)


def test_smooth_regular_weekly_demand():
    series = [10, 11, 9, 10, 12, 10, 11, 9]
    stats = demand_statistics(series)
    assert stats.demand_class == "smooth"
    assert stats.adi == pytest.approx(1.0)
    assert stats.cv2_size < CV2_CUTOFF
    assert stats.mean == pytest.approx(demand_mean(series))


def test_intermittent_constant_size_sparse_hits():
    # Demand every third week, always 10 units. ADI = 3, CV^2 of sizes = 0.
    series = [10, 0, 0, 10, 0, 0, 10, 0, 0, 10, 0, 0]
    stats = demand_statistics(series)
    assert stats.adi == pytest.approx(3.0)
    assert stats.adi >= ADI_CUTOFF
    assert stats.cv2_size == pytest.approx(0.0)
    assert stats.demand_class == "intermittent"


def test_erratic_every_week_volatile_size():
    series = [1, 20, 1, 20, 1, 20, 1, 20]
    stats = demand_statistics(series)
    assert stats.adi == pytest.approx(1.0)
    assert stats.cv2_size >= CV2_CUTOFF
    assert stats.demand_class == "erratic"


def test_lumpy_sparse_and_volatile():
    series = [20, 0, 0, 0, 5, 0, 0, 40]
    stats = demand_statistics(series)
    assert stats.adi >= ADI_CUTOFF
    assert stats.cv2_size >= CV2_CUTOFF
    assert stats.demand_class == "lumpy"


def test_zero_demand_is_intermittent_matching_dbt():
    series = [0.0, 0.0, 0.0, 0.0]
    stats = demand_statistics(series)
    assert stats.mean == 0.0
    assert stats.std == 0.0
    assert math.isinf(stats.adi)
    assert stats.cv2_size == 0.0
    assert stats.demand_class == "intermittent"
    assert classify_demand(series) == "intermittent"


def test_single_observation_zero_variance_and_smooth_if_positive():
    stats = demand_statistics([12.0])
    assert stats.n_periods == 1
    assert stats.std == 0.0
    assert stats.cv == 0.0
    assert stats.adi == pytest.approx(1.0)
    assert stats.cv2_size == 0.0
    assert stats.demand_class == "smooth"


def test_single_zero_observation_is_intermittent():
    stats = demand_statistics([0.0])
    assert stats.demand_class == "intermittent"
    assert stats.std == 0.0


def test_dbt_unit_test_fixtures_match_int_demand_variability():
    """Same weekly series as models/intermediate/_intermediate__models.yml."""
    assert classify_demand([10, 10, 10, 10]) == "smooth"
    assert classify_demand([1, 1, 1, 20]) == "erratic"
    assert classify_demand([10, 0, 0, 10]) == "intermittent"
    assert classify_demand([1, 0, 0, 20]) == "lumpy"
    assert classify_demand([7]) == "smooth"
    assert classify_demand([0, 0]) == "intermittent"
    assert classify_demand([1, 1, 1, 1000]) == "erratic"


def test_cutoffs_are_inclusive_on_the_smooth_side():
    # dbt: ADI <= 1.32 and CV² <= 0.49 → smooth
    assert classify_demand(adi=1.32, cv2_size=0.49, n_nonzero=10) == "smooth"
    assert classify_demand(adi=1.32, cv2_size=0.4901, n_nonzero=10) == "erratic"
    assert classify_demand(adi=1.3201, cv2_size=0.49, n_nonzero=10) == "intermittent"
    assert classify_demand(adi=1.3201, cv2_size=0.4901, n_nonzero=10) == "lumpy"


def test_sample_std_matches_ddof_1():
    series = [1.0, 3.0, 5.0]
    assert demand_std(series) == pytest.approx(float(np.std(series, ddof=1)))
    assert demand_mean(series) == pytest.approx(3.0)


def test_cv_zero_when_mean_and_std_zero():
    assert coefficient_of_variation(mean=0.0, std=0.0) == 0.0


def test_cv_inf_when_mean_zero_positive_std():
    assert math.isinf(coefficient_of_variation(mean=0.0, std=1.0))


def test_adi_counts_strictly_positive_periods():
    series = [0.0, 2.0, 0.0, 2.0]
    assert average_demand_interval(series) == pytest.approx(2.0)
    assert cv_squared_demand_size(series) == pytest.approx(0.0)


def test_empty_series_raises():
    with pytest.raises(ValueError, match="empty"):
        demand_statistics([])


def test_all_nan_raises():
    with pytest.raises(ValueError, match="finite"):
        demand_statistics([float("nan"), float("inf")])
