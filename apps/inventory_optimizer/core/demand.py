"""Demand statistics and Syntetos–Boylan–Croston classification.

dbt is the source of truth for ``demand_class`` on warehouse tables such as
``agg_sku_location_demand_weekly``. This module re-implements the same rules so
the optimizer can classify a weekly history without a warehouse round-trip
(sample mode, what-if shocks, unit tests). If a SKU's warehouse class and this
function ever disagree, trust dbt and treat that as a bug in this file.

Classification cut-offs follow Syntetos, Boylan & Croston (2005), "On the
categorization of demand patterns", Journal of the Operational Research
Society 56(4): 463–469:

    Smooth        ADI <  1.32  and  CV² <  0.49
    Erratic       ADI <  1.32  and  CV² >= 0.49
    Intermittent  ADI >= 1.32  and  CV² <  0.49
    Lumpy         ADI >= 1.32  and  CV² >= 0.49

ADI is the average demand interval (periods per non-zero observation).
CV² is the squared coefficient of variation of *non-zero demand sizes*, not of
the zero-inflated series. Sample standard deviation uses ddof=1, matching
Snowflake ``STDDEV`` / ``STDDEV_SAMP``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

ADI_CUTOFF = 1.32
CV2_CUTOFF = 0.49

DEMAND_CLASSES = (
    "smooth",
    "erratic",
    "intermittent",
    "lumpy",
)


@dataclass(frozen=True)
class DemandStats:
    """Summary statistics for one SKU × location weekly demand history."""

    n_periods: int
    n_nonzero: int
    mean: float
    std: float
    cv: float
    adi: float
    cv2_size: float
    demand_class: str


def _as_finite_array(demand: np.ndarray | list[float] | tuple[float, ...]) -> np.ndarray:
    """Return a 1-d float array, dropping NaN/inf observations."""
    arr = np.asarray(demand, dtype=float).ravel()
    if arr.size == 0:
        raise ValueError("demand series is empty")
    finite = arr[np.isfinite(arr)]
    if finite.size == 0:
        raise ValueError("demand series contains no finite observations")
    return finite


def demand_mean(demand: np.ndarray | list[float] | tuple[float, ...]) -> float:
    """Arithmetic mean of weekly demand, including zero-demand periods.

    Formula: ``d_bar = (1/n) * sum_t D_t``.

    Assumption: missing weeks have already been filled with zeros (a complete
    calendar spine). That is how ``agg_sku_location_demand_weekly`` is built.
    """
    return float(np.mean(_as_finite_array(demand)))


def demand_std(demand: np.ndarray | list[float] | tuple[float, ...]) -> float:
    """Sample standard deviation of weekly demand, including zeros.

    Formula: ``sigma_d = sqrt( sum_t (D_t - d_bar)^2 / (n - 1) )``.

    Degenerate cases:
        * n < 2 → 0.0 (Snowflake ``STDDEV`` of a single row is NULL; we treat
          that as no evidence of variability rather than NaN).
        * constant series → 0.0.
    """
    arr = _as_finite_array(demand)
    if arr.size < 2:
        return 0.0
    return float(np.std(arr, ddof=1))


def coefficient_of_variation(
    demand: np.ndarray | list[float] | tuple[float, ...] | None = None,
    *,
    mean: float | None = None,
    std: float | None = None,
) -> float:
    """Coefficient of variation of the zero-inflated weekly series.

    Formula: ``CV = sigma_d / d_bar``.

    Returns 0.0 when both mean and std are 0 (the zero-demand series).
    Returns ``inf`` when mean is 0 and std is positive.
    """
    if mean is None or std is None:
        if demand is None:
            raise ValueError("pass demand, or both mean and std")
        mean = demand_mean(demand)
        std = demand_std(demand)
    if mean == 0.0:
        return 0.0 if std == 0.0 else float("inf")
    return float(std / mean)


def average_demand_interval(demand: np.ndarray | list[float] | tuple[float, ...]) -> float:
    """Average Demand Interval (ADI).

    Formula: ``ADI = n / n_nonzero`` where ``n_nonzero = count(D_t > 0)``.

    This is the discrete-time form of Croston's interval length: the average
    number of review periods between successive positive-demand periods.
    Syntetos, Boylan & Croston (2005) use the same ratio as the ADI cut-off
    statistic.

    Degenerate case: no positive observations → ``inf``.
    """
    arr = _as_finite_array(demand)
    n_nonzero = int(np.sum(arr > 0.0))
    if n_nonzero == 0:
        return float("inf")
    return float(arr.size / n_nonzero)


def cv_squared_demand_size(demand: np.ndarray | list[float] | tuple[float, ...]) -> float:
    """Squared CV of non-zero demand sizes (SBC ``CV^2``).

    Formula: ``CV^2 = (s / m)^2`` where ``m`` and ``s`` are the sample mean and
    sample std of ``{D_t : D_t > 0}``.

    Zeros are excluded. This is the statistic Syntetos et al. (2005) compare
    to 0.49; it is *not* the CV of the zero-inflated series used in safety
    stock.

    Degenerate cases:
        * fewer than two positive observations → 0.0 (no evidence of size
          variability; classification then hinges on ADI alone).
    """
    arr = _as_finite_array(demand)
    sizes = arr[arr > 0.0]
    if sizes.size < 2:
        return 0.0
    mean_size = float(np.mean(sizes))
    if mean_size == 0.0:
        return 0.0
    std_size = float(np.std(sizes, ddof=1))
    return float((std_size / mean_size) ** 2)


def classify_demand(
    demand: np.ndarray | list[float] | tuple[float, ...] | None = None,
    *,
    adi: float | None = None,
    cv2_size: float | None = None,
    n_nonzero: int | None = None,
) -> str:
    """Map ADI and CV² onto ``smooth`` / ``erratic`` / ``intermittent`` / ``lumpy``.

    Mirrors ``int_demand_variability`` exactly — dbt is the source of truth:

        when nonzero_demand_weeks = 0 then 'intermittent'
        when ADI <= 1.32 and CV² <= 0.49 then 'smooth'
        when ADI <= 1.32 and CV² >  0.49 then 'erratic'
        when ADI >  1.32 and CV² <= 0.49 then 'intermittent'
        else 'lumpy'

    Boundaries are ``<=`` on the smooth side, matching the dbt case-when
    (not ``<``). All-zero history is intermittent, not a fifth class.
    """
    if adi is None or cv2_size is None or n_nonzero is None:
        if demand is None:
            raise ValueError("pass demand, or adi, cv2_size, and n_nonzero")
        arr = _as_finite_array(demand)
        n_nonzero = int(np.sum(arr > 0.0))
        adi = average_demand_interval(arr)
        cv2_size = cv_squared_demand_size(arr)

    if n_nonzero == 0:
        return "intermittent"

    frequent = adi <= ADI_CUTOFF
    stable = cv2_size <= CV2_CUTOFF
    if frequent and stable:
        return "smooth"
    if frequent and not stable:
        return "erratic"
    if (not frequent) and stable:
        return "intermittent"
    return "lumpy"


def demand_statistics(demand: np.ndarray | list[float] | tuple[float, ...]) -> DemandStats:
    """Compute the full demand-stat bundle used by policy selection.

    All-period mean/std/CV feed the safety-stock formula. ADI and CV² of
    demand sizes feed classification, which then routes the SKU to a normal,
    Poisson, or negative-binomial lead-time demand model.
    """
    arr = _as_finite_array(demand)
    n_nonzero = int(np.sum(arr > 0.0))
    mean = demand_mean(arr)
    std = demand_std(arr)
    adi = average_demand_interval(arr)
    cv2 = cv_squared_demand_size(arr)
    return DemandStats(
        n_periods=int(arr.size),
        n_nonzero=n_nonzero,
        mean=mean,
        std=std,
        cv=coefficient_of_variation(mean=mean, std=std),
        adi=adi,
        cv2_size=cv2,
        demand_class=classify_demand(adi=adi, cv2_size=cv2, n_nonzero=n_nonzero),
    )
