"""Echelon demand rollup and risk-pooling (square-root law).

Risk pooling compares holding safety stock at each branch versus holding a
single pooled buffer at the regional DC. Under independent demand the
pooled lead-time-demand standard deviation is the Euclidean norm of the
location sigmas, which is the square-root law:

    sigma_pooled = sqrt(sum_i sigma_i^2)
    SS_pooled    = z * sigma_pooled

For n identical independent locations this collapses to
``SS_pooled = SS_branch * sqrt(n)``, so the inventory reduction at equal
service is ``1 - 1/sqrt(n)``.

Textbook anchors
----------------
* Eppen (1979), "Effects of Centralization on Expected Costs in a
  Multi-Location Newsboy Problem", *Management Science* 25(5): 498–501.
* Maister (1976) square-root law of locations, *International Journal of
  Physical Distribution*.
* Chopra & Meindl, *Supply Chain Management*, risk-pooling chapter.

Assumptions: equal cycle service level (same z) at the decentralized and
pooled designs; no material change in replenishment lead time when stock
moves up a level (a conservative demo — if the DC is faster, pooling wins
by even more). Correlation is an explicit argument; the square-root law
is the independent (rho = 0) case.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import sqrt

import numpy as np

from core.policy import z_from_service_level


@dataclass(frozen=True)
class LocationSigma:
    """One location's contribution to a pooling comparison."""

    location_id: str
    sigma_dl: float
    unit_cost: float = 1.0
    region_id: str = ""
    echelon: str = "branch"


@dataclass(frozen=True)
class PoolingResult:
    """Decentralized vs regional-DC pooled safety stock at equal CSL."""

    n_locations: int
    z: float
    service_level: float
    sigma_decentralized_sum: float
    sigma_pooled: float
    safety_stock_decentralized: float
    safety_stock_pooled: float
    units_reduction: float
    units_reduction_pct: float
    dollars_decentralized: float
    dollars_pooled: float
    dollars_reduction: float
    square_root_law_ratio: float
    correlation: float


def square_root_law_ratio(n_locations: int) -> float:
    """Pooled / decentralized safety-stock ratio for n identical locations.

    Formula: ``SS_pooled / SS_decentral = 1 / sqrt(n)``.

    Maister (1976); equivalent to Eppen (1979) under i.i.d. demand and
    identical holding costs. ``n <= 0`` raises; ``n == 1`` returns 1.0
    (no pooling benefit).
    """
    n = int(n_locations)
    if n <= 0:
        raise ValueError("n_locations must be positive")
    return float(1.0 / sqrt(n))


def sigma_pooled_independent(sigmas: np.ndarray | list[float] | tuple[float, ...]) -> float:
    """Pooled lead-time-demand std under independent location demand.

    Formula: ``sigma_pool = sqrt(sum_i sigma_i^2)``.

    Empty input → 0. Negative sigmas are treated as 0.
    """
    arr = np.asarray(sigmas, dtype=float).ravel()
    if arr.size == 0:
        return 0.0
    arr = np.clip(arr, 0.0, None)
    return float(np.sqrt(np.sum(arr**2)))


def sigma_pooled_equicorrelated(
    sigmas: np.ndarray | list[float] | tuple[float, ...],
    correlation: float,
) -> float:
    """Pooled std with common pairwise correlation ``rho``.

    Formula:
        Var_pool = sum_i sigma_i^2 + 2 rho * sum_{i<j} sigma_i sigma_j

    ``rho = 0`` recovers the square-root law. ``rho = 1`` recovers
    ``sum sigma_i`` (no pooling benefit). ``rho`` is clipped to ``[-1, 1]``.
    """
    arr = np.clip(np.asarray(sigmas, dtype=float).ravel(), 0.0, None)
    rho = float(np.clip(correlation, -1.0, 1.0))
    if arr.size == 0:
        return 0.0
    if arr.size == 1:
        return float(arr[0])
    variance = float(np.sum(arr**2))
    pair = 0.0
    for i in range(arr.size):
        for j in range(i + 1, arr.size):
            pair += float(arr[i] * arr[j])
    variance += 2.0 * rho * pair
    return float(sqrt(max(variance, 0.0)))


def echelon_demand_rollup(
    child_means: np.ndarray | list[float] | tuple[float, ...],
    child_variances: np.ndarray | list[float] | tuple[float, ...],
    *,
    independent: bool = True,
    correlation: float = 0.0,
) -> tuple[float, float]:
    """Roll branch demand up to a parent DC.

    Formula:
        mu_parent  = sum_i mu_i
        var_parent = sum_i var_i                         (independent)
                   = 1' Σ 1  with equicorrelation rho    (otherwise)

    Returns ``(mean, std)`` of the parent. Variances < 0 are treated as 0.
    """
    means = np.asarray(child_means, dtype=float).ravel()
    variances = np.clip(np.asarray(child_variances, dtype=float).ravel(), 0.0, None)
    if means.size != variances.size:
        raise ValueError("child_means and child_variances must be the same length")
    parent_mean = float(np.sum(means))
    if means.size == 0:
        return 0.0, 0.0
    sigmas = np.sqrt(variances)
    if independent:
        parent_std = sigma_pooled_independent(sigmas)
    else:
        parent_std = sigma_pooled_equicorrelated(sigmas, correlation)
    return parent_mean, parent_std


def pooling_comparison(
    locations: list[LocationSigma],
    service_level: float,
    *,
    correlation: float = 0.0,
) -> PoolingResult:
    """Compare branch-held vs DC-pooled safety stock at equal service.

    Decentralized SS is ``z * sum_i sigma_i`` (each branch meets CSL on its
    own). Pooled SS is ``z * sigma_pool``. The unit reduction and the dollar
    reduction (using each location's unit cost, averaged for the pooled
    buffer) are the quantities the Network page will show.

    Degenerate cases:
        * no locations → zeros.
        * one location → reduction = 0.
        * all sigmas zero → both designs hold 0.
    """
    z = z_from_service_level(service_level) if locations else 0.0
    sigmas = np.array([max(loc.sigma_dl, 0.0) for loc in locations], dtype=float)
    costs = np.array([max(loc.unit_cost, 0.0) for loc in locations], dtype=float)
    n = int(sigmas.size)
    if n == 0:
        return PoolingResult(
            n_locations=0,
            z=0.0,
            service_level=float(service_level),
            sigma_decentralized_sum=0.0,
            sigma_pooled=0.0,
            safety_stock_decentralized=0.0,
            safety_stock_pooled=0.0,
            units_reduction=0.0,
            units_reduction_pct=0.0,
            dollars_decentralized=0.0,
            dollars_pooled=0.0,
            dollars_reduction=0.0,
            square_root_law_ratio=1.0,
            correlation=float(correlation),
        )

    sigma_sum = float(np.sum(sigmas))
    sigma_pool = sigma_pooled_equicorrelated(sigmas, correlation)
    ss_dec = z * sigma_sum
    ss_pool = z * sigma_pool
    units_reduction = ss_dec - ss_pool
    pct = (units_reduction / ss_dec) if ss_dec > 0.0 else 0.0
    dollars_dec = float(z * np.sum(sigmas * costs))
    avg_cost = float(np.mean(costs)) if costs.size else 0.0
    dollars_pool = ss_pool * avg_cost
    srl = square_root_law_ratio(n)
    return PoolingResult(
        n_locations=n,
        z=z,
        service_level=float(service_level),
        sigma_decentralized_sum=sigma_sum,
        sigma_pooled=float(sigma_pool),
        safety_stock_decentralized=float(ss_dec),
        safety_stock_pooled=float(ss_pool),
        units_reduction=float(units_reduction),
        units_reduction_pct=float(pct),
        dollars_decentralized=float(dollars_dec),
        dollars_pooled=float(dollars_pool),
        dollars_reduction=float(dollars_dec - dollars_pool),
        square_root_law_ratio=srl,
        correlation=float(np.clip(correlation, -1.0, 1.0)),
    )
