"""Safety stock, reorder point, order quantity, and budgeted service allocation.

Lead-time demand is modeled with *both* demand variability and lead-time
variability. The naive ``z * sigma_d * sqrt(L)`` form is intentionally not
used: for Meridian's unreliable suppliers, ``d_bar^2 * sigma_L^2`` dominates
``L * sigma_d^2``. That comparison is a core teaching point of this demo.

Textbook anchors
----------------
* Combined demand/lead-time uncertainty:
  Silver, Pyke & Thomas, *Inventory and Production Management in Supply
  Chains*, and equivalently Hopp & Spearman, *Factory Physics*:

      sigma_DL = sqrt(L * sigma_d^2 + d_bar^2 * sigma_L^2)
      SS       = z * sigma_DL                 (normal, Type-I / CSL)
      ROP      = d_bar * L + SS

* Standard normal loss / Type-II fill rate:
  Hadley & Whitin; Axsäter, *Inventory Control*. Expected units short per
  replenishment cycle ``n(s) = sigma_DL * G(z)`` with
  ``G(z) = phi(z) - z * (1 - Phi(z))``. Fill rate ``= 1 - n(s) / Q``.

* Intermittent / lumpy demand:
  Croston (1972); Syntetos, Boylan & Croston (2005). The normal
  approximation is a poor model of lead-time demand when many periods are
  zero. We use Poisson when variance ≤ mean and negative binomial when
  overdispersed, and size the reorder point to a fill-rate target.

* EOQ:
  Harris (1913) / Wilson: ``Q* = sqrt(2 * D * S / H)``, then rounded up to
  the supplier's minimum order quantity and order multiple.

* Budgeted multi-item service:
  Greedy allocation on marginal fill-rate per dollar of safety-stock
  investment. Near-optimal for concave fill-rate-vs-stock curves (classic
  multi-item newsboy / "equimarginal" argument; see Porteus, *Foundations of
  Stochastic Inventory Theory*). An LP is not required at this grain.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from math import ceil, sqrt

import numpy as np
from scipy import stats

from core.demand import DemandStats, demand_statistics

DEFAULT_HOLDING_RATE = 0.25
DEFAULT_SHORTAGE_PENALTY_RATE = 1.0
WEEKS_PER_YEAR = 52

# Service-level ladder used by the greedy allocator and efficient frontier.
SERVICE_LEVEL_GRID = (
    0.80,
    0.85,
    0.90,
    0.925,
    0.95,
    0.97,
    0.98,
    0.99,
    0.995,
)


@dataclass(frozen=True)
class SkuLocationParams:
    """Inputs required to recommend a policy for one SKU × location.

    Lead times are in the same time unit as the demand series (weeks).
    ``order_cost`` is $ per replenishment. ``holding_rate`` is $ holding cost
    per year as a fraction of unit cost (e.g. 0.25).
    """

    sku_id: str
    location_id: str
    demand_mean: float
    demand_std: float
    demand_class: str
    lead_time_mean: float
    lead_time_std: float
    unit_cost: float
    target_service_level: float = 0.95
    min_order_qty: float = 1.0
    order_multiple: float = 1.0
    order_cost: float = 50.0
    holding_rate: float = DEFAULT_HOLDING_RATE
    current_safety_stock: float = 0.0
    current_reorder_point: float = 0.0
    current_order_qty: float = 0.0
    category: str = ""
    supplier_id: str = ""
    sourcing_region: str = ""
    echelon: str = ""
    region_id: str = ""
    abc_class: str = ""
    annual_demand: float | None = None

    def yearly_demand(self) -> float:
        if self.annual_demand is not None:
            return float(self.annual_demand)
        return float(self.demand_mean * WEEKS_PER_YEAR)


@dataclass(frozen=True)
class PolicyRecommendation:
    """Recommended (and current) policy for one SKU × location."""

    sku_id: str
    location_id: str
    demand_class: str
    method: str
    demand_mean: float
    demand_std: float
    lead_time_mean: float
    lead_time_std: float
    sigma_dl: float
    mu_dl: float
    z: float | None
    safety_stock: float
    reorder_point: float
    order_quantity: float
    eoq_unrounded: float
    target_service_level: float
    service_level_kind: str
    achieved_fill_rate: float
    achieved_csl: float
    unit_cost: float
    current_safety_stock: float
    current_reorder_point: float
    current_order_qty: float
    current_fill_rate: float
    current_csl: float
    safety_stock_delta_units: float
    safety_stock_delta_dollars: float
    annual_net_benefit: float
    overdispersion: float

    @property
    def fill_rate_delta(self) -> float:
        return self.achieved_fill_rate - self.current_fill_rate


@dataclass(frozen=True)
class FrontierPoint:
    """One point on the fill-rate vs inventory-investment curve."""

    investment: float
    weighted_fill_rate: float
    n_upgrades: int


@dataclass(frozen=True)
class AllocationResult:
    """Budget-constrained service-level assignment across SKU × locations."""

    recommendations: tuple[PolicyRecommendation, ...]
    investment: float
    weighted_fill_rate: float
    budget: float
    unallocated_budget: float


def z_from_service_level(service_level: float) -> float:
    """Standard-normal z for a Type-I cycle service level.

    Formula: ``z = Phi^{-1}(CSL)``.

    Assumptions: lead-time demand is continuous and approximately normal;
    ``service_level`` is a probability in (0, 1). Values are clipped to
    ``(1e-9, 1 - 1e-9)`` so ``ppf`` stays finite.
    """
    p = float(np.clip(service_level, 1e-9, 1.0 - 1e-9))
    return float(stats.norm.ppf(p))


def sigma_demand_over_lead_time(
    demand_mean: float,
    demand_std: float,
    lead_time_mean: float,
    lead_time_std: float,
) -> float:
    """Combined demand-over-lead-time standard deviation.

    Formula (Silver, Pyke & Thomas; Hopp & Spearman):

        sigma_DL = sqrt( L * sigma_d^2 + d_bar^2 * sigma_L^2 )

    where ``L`` and ``sigma_L`` are in the same time unit as the demand
    series (weeks here). This is *not* ``sigma_d * sqrt(L)``. The second term
    is lead-time uncertainty and is the dominant driver of safety stock for
    Meridian suppliers with erratic transit times.

    Degenerate cases:
        * L = 0 and sigma_L = 0 → 0.
        * L = 0 and sigma_L > 0 → ``d_bar * sigma_L`` (uncertain delay even
          though mean lead time is zero — unusual, but the formula still
          holds).
        * zero demand variance and zero lead-time variance → 0.
    """
    d_bar = max(float(demand_mean), 0.0)
    sigma_d = max(float(demand_std), 0.0)
    lead_time = max(float(lead_time_mean), 0.0)
    sigma_l = max(float(lead_time_std), 0.0)
    variance = lead_time * sigma_d**2 + d_bar**2 * sigma_l**2
    return float(sqrt(max(variance, 0.0)))


def safety_stock_normal(
    demand_mean: float,
    demand_std: float,
    lead_time_mean: float,
    lead_time_std: float,
    service_level: float,
) -> float:
    """Normal-approximation safety stock with demand and lead-time variance.

    Formula: ``SS = z * sigma_DL`` with ``z = Phi^{-1}(CSL)`` and
    ``sigma_DL`` from :func:`sigma_demand_over_lead_time`.

    Assumptions: Type-I cycle service level; continuous normal lead-time
    demand. Do not use this for intermittent or lumpy SKUs — those are
    routed to Poisson / negative-binomial fill-rate logic.

    Degenerate cases: zero combined variance → SS = 0 regardless of z.
    """
    z = z_from_service_level(service_level)
    sigma_dl = sigma_demand_over_lead_time(
        demand_mean, demand_std, lead_time_mean, lead_time_std
    )
    return float(z * sigma_dl)


def reorder_point(
    demand_mean: float,
    lead_time_mean: float,
    safety_stock: float,
) -> float:
    """Reorder point = expected demand over lead time + safety stock.

    Formula: ``ROP = d_bar * L + SS``.

    Degenerate case: L = 0 → ROP = SS (including SS = 0).
    """
    mu_dl = max(float(demand_mean), 0.0) * max(float(lead_time_mean), 0.0)
    return float(mu_dl + safety_stock)


def economic_order_quantity(
    annual_demand: float,
    order_cost: float,
    holding_cost_per_unit_year: float,
) -> float:
    """Harris/Wilson EOQ, unrounded.

    Formula: ``Q* = sqrt(2 * D * S / H)``.

    Assumptions: constant deterministic demand, fixed ordering cost S, linear
    holding cost H per unit-year, no quantity discounts. This is a cycle-stock
    approximation; uncertainty is handled entirely in safety stock.

    Degenerate cases:
        * D <= 0 → 0.
        * S <= 0 → 0 (no reason to batch).
        * H <= 0 → ``D`` (hold nothing extra; order the year's demand once —
          the unconstrained EOQ diverges).
    """
    d = float(annual_demand)
    s = float(order_cost)
    h = float(holding_cost_per_unit_year)
    if d <= 0.0 or s <= 0.0:
        return 0.0
    if h <= 0.0:
        return d
    return float(sqrt(2.0 * d * s / h))


def round_order_quantity(
    eoq: float,
    min_order_qty: float = 1.0,
    order_multiple: float = 1.0,
) -> float:
    """Round EOQ up to the supplier MOQ and order multiple.

    Procedure:
        1. ``Q = max(EOQ, MOQ, 0)``
        2. If ``multiple > 0``, ``Q = ceil(Q / multiple) * multiple``

    A multiple of 0 or negative is treated as "no multiple constraint".
    The result is at least the multiple when EOQ and MOQ are both 0 but a
    multiple is specified, otherwise 0.
    """
    moq = max(float(min_order_qty), 0.0)
    qty = max(float(eoq), moq)
    multiple = float(order_multiple)
    if multiple > 0.0:
        if qty <= 0.0:
            return 0.0
        qty = float(ceil(qty / multiple - 1e-12) * multiple)
    return float(qty)


def _standard_normal_loss(z: float) -> float:
    """Unit normal loss function ``G(z) = phi(z) - z * (1 - Phi(z))``."""
    return float(stats.norm.pdf(z) - z * stats.norm.sf(z))


def _mu_sigma_dl(params: SkuLocationParams) -> tuple[float, float]:
    mu = max(params.demand_mean, 0.0) * max(params.lead_time_mean, 0.0)
    sigma = sigma_demand_over_lead_time(
        params.demand_mean,
        params.demand_std,
        params.lead_time_mean,
        params.lead_time_std,
    )
    return mu, sigma


def _discrete_lead_time_dist(mu: float, sigma: float):
    """Poisson if variance ≤ mean, otherwise negative binomial.

    Negative binomial uses scipy's ``nbinom(n, p)`` parameterization
    (number of failures before ``n`` successes):

        p = mu / sigma^2
        n = mu^2 / (sigma^2 - mu)

    so that ``E[X] = mu`` and ``Var[X] = sigma^2``. When ``sigma^2 <= mu``
    the series is not overdispersed and Poisson(mu) is the maximum-entropy
    count model with that mean (and is the classical intermittent-demand
    approximation).
    """
    mu = max(float(mu), 0.0)
    var = max(float(sigma) ** 2, 0.0)
    if mu <= 0.0:
        return "degenerate", None
    if var <= mu + 1e-12:
        return "poisson", stats.poisson(mu=mu)
    p = float(np.clip(mu / var, 1e-12, 1.0 - 1e-12))
    n = mu * p / (1.0 - p)
    n = max(float(n), 1e-6)
    return "negbin", stats.nbinom(n=n, p=p)


def _expected_shortfall_discrete(dist, s: float) -> float:
    """``E[(X - s)+]`` for a discrete non-negative distribution.

    For integer-valued X and integer s >= 0:
        E[(X - s)+] = sum_{k=s}^{∞} P(X > k)
    """
    threshold = int(max(np.floor(s), 0))
    upper = int(max(threshold + 1, np.ceil(dist.ppf(0.99999)) + 8))
    ks = np.arange(threshold, upper + 1)
    return float(np.sum(dist.sf(ks)))


def expected_shortage(
    mu_dl: float,
    sigma_dl: float,
    reorder_point_units: float,
    method: str,
) -> float:
    """Expected units short per replenishment cycle, ``n(ROP)``.

    Normal: ``n(s) = sigma_DL * G(z)``, ``z = (s - mu_DL) / sigma_DL``.
    Poisson / NB: summed discrete survival function.

    Degenerate: sigma = 0 → ``max(mu - s, 0)``.
    """
    mu = max(float(mu_dl), 0.0)
    sigma = max(float(sigma_dl), 0.0)
    s = float(reorder_point_units)
    if method == "normal_csl":
        if sigma <= 0.0:
            return max(mu - s, 0.0)
        z = (s - mu) / sigma
        return float(sigma * _standard_normal_loss(z))
    kind, dist = _discrete_lead_time_dist(mu, sigma)
    if kind == "degenerate" or dist is None:
        return max(mu - s, 0.0)
    return _expected_shortfall_discrete(dist, s)


def _fill_rate_from_shortage(shortage: float, order_qty: float) -> float:
    if order_qty <= 0.0:
        return 0.0 if shortage > 0.0 else 1.0
    return float(np.clip(1.0 - shortage / order_qty, 0.0, 1.0))


def achieved_fill_rate(
    params: SkuLocationParams,
    reorder_point_units: float,
    order_qty: float,
    method: str,
) -> float:
    """Type-II item fill rate under a given (ROP, Q) policy.

    Formula: ``FR = 1 - n(ROP) / Q``.
    """
    mu, sigma = _mu_sigma_dl(params)
    shortage = expected_shortage(mu, sigma, reorder_point_units, method)
    return _fill_rate_from_shortage(shortage, order_qty)


def achieved_cycle_service_level(
    params: SkuLocationParams,
    reorder_point_units: float,
    method: str,
) -> float:
    """Type-I cycle service level ``P(lead-time demand <= ROP)``."""
    mu, sigma = _mu_sigma_dl(params)
    s = float(reorder_point_units)
    if method == "normal_csl":
        if sigma <= 0.0:
            return 1.0 if s >= mu else 0.0
        return float(stats.norm.cdf((s - mu) / sigma))
    kind, dist = _discrete_lead_time_dist(mu, sigma)
    if kind == "degenerate" or dist is None:
        return 1.0 if s >= mu else 0.0
    return float(dist.cdf(np.floor(s)))


def _select_method(demand_class: str, mu_dl: float, sigma_dl: float) -> str:
    """Route a SKU to a lead-time demand model.

    Smooth / erratic: normal Type-I safety stock (the ``z * sigma_DL`` form).
    Intermittent: Poisson fill-rate, or NB if overdispersed.
    Lumpy: negative binomial fill-rate, or Poisson if not overdispersed.
    Zero-demand series still classify as intermittent in dbt; the zero mean
    short-circuit in :func:`recommend_policy` then forces SS = 0.
    """
    var = sigma_dl**2
    overdispersed = var > mu_dl + 1e-12 and mu_dl > 0.0
    if demand_class in {"smooth", "erratic"}:
        return "normal_csl"
    if demand_class == "intermittent":
        return "negbin_fill_rate" if overdispersed else "poisson_fill_rate"
    if demand_class == "lumpy":
        return "negbin_fill_rate" if overdispersed else "poisson_fill_rate"
    return "normal_csl"


def _discrete_rop_for_fill_rate(
    mu: float,
    sigma: float,
    order_qty: float,
    target_fill_rate: float,
) -> tuple[float, str]:
    """Smallest integer ROP whose fill rate meets the target."""
    kind, dist = _discrete_lead_time_dist(mu, sigma)
    if kind == "degenerate" or dist is None:
        return 0.0, "poisson_fill_rate"
    method = "poisson_fill_rate" if kind == "poisson" else "negbin_fill_rate"
    target = float(np.clip(target_fill_rate, 0.0, 1.0))
    upper = int(max(0, np.ceil(dist.ppf(0.99999)) + 16))
    best_r = float(upper)
    for r in range(0, upper + 1):
        n_s = _expected_shortfall_discrete(dist, r)
        fr = _fill_rate_from_shortage(n_s, order_qty)
        if fr >= target - 1e-12:
            return float(r), method
        best_r = float(r)
    return best_r, method


def _order_quantity_for(params: SkuLocationParams) -> tuple[float, float]:
    holding = params.holding_rate * params.unit_cost
    eoq = economic_order_quantity(params.yearly_demand(), params.order_cost, holding)
    qty = round_order_quantity(eoq, params.min_order_qty, params.order_multiple)
    if qty <= 0.0 and params.yearly_demand() > 0.0:
        qty = max(params.min_order_qty, params.order_multiple, 1.0)
        qty = round_order_quantity(qty, params.min_order_qty, params.order_multiple)
    return eoq, qty


def _annual_shortage_cost(
    params: SkuLocationParams,
    shortage_per_cycle: float,
    order_qty: float,
    penalty_rate: float = DEFAULT_SHORTAGE_PENALTY_RATE,
) -> float:
    if order_qty <= 0.0:
        cycles = 0.0 if params.yearly_demand() <= 0.0 else 1.0
    else:
        cycles = params.yearly_demand() / order_qty
    return float(cycles * shortage_per_cycle * params.unit_cost * penalty_rate)


def _annual_holding_cost(safety_stock: float, params: SkuLocationParams) -> float:
    return float(max(safety_stock, 0.0) * params.unit_cost * params.holding_rate)


def recommend_policy(
    params: SkuLocationParams,
    *,
    target_service_level: float | None = None,
    demand: np.ndarray | list[float] | tuple[float, ...] | None = None,
    stats: DemandStats | None = None,
) -> PolicyRecommendation:
    """Recommend SS, ROP, and Q for one SKU × location.

    Routing:
        * ``smooth`` / ``erratic``: ``SS = z * sigma_DL`` (Type-I CSL).
        * ``intermittent`` / ``lumpy``: discrete fill-rate ROP via Poisson
          or negative binomial. ``SS = ROP - mu_DL``.
        * zero mean and std (dbt still labels these intermittent): SS = 0,
          ROP = 0, Q = 0.

    ``method`` on the result is the flag the UI should show per SKU.
    Passing ``demand`` or ``stats`` overrides ``demand_class`` / mean / std
    from ``params`` so a what-if series can be classified on the fly.
    """
    working = params
    if stats is not None or demand is not None:
        computed = stats if stats is not None else demand_statistics(demand)
        working = replace(
            params,
            demand_mean=computed.mean,
            demand_std=computed.std,
            demand_class=computed.demand_class,
        )
    target = (
        working.target_service_level
        if target_service_level is None
        else float(target_service_level)
    )
    mu, sigma = _mu_sigma_dl(working)
    method = _select_method(working.demand_class, mu, sigma)
    eoq, qty = _order_quantity_for(working)

    if working.demand_mean <= 0.0 and working.demand_std <= 0.0:
        rec_ss = 0.0
        rec_rop = 0.0
        z: float | None = None
        method = "normal_csl"
        qty = 0.0
        eoq = 0.0
        service_kind = "cycle_service_level"
    elif method == "normal_csl":
        z = z_from_service_level(target)
        rec_ss = z * sigma
        rec_rop = reorder_point(working.demand_mean, working.lead_time_mean, rec_ss)
        service_kind = "cycle_service_level"
    else:
        z = None
        rec_rop, method = _discrete_rop_for_fill_rate(mu, sigma, qty, target)
        rec_ss = rec_rop - mu
        service_kind = "fill_rate"

    rec_fr = achieved_fill_rate(working, rec_rop, max(qty, 1.0) if qty == 0 else qty, method)
    rec_csl = achieved_cycle_service_level(working, rec_rop, method)

    cur_q = working.current_order_qty if working.current_order_qty > 0 else qty
    cur_rop = (
        working.current_reorder_point
        if working.current_reorder_point > 0
        else reorder_point(
            working.demand_mean, working.lead_time_mean, working.current_safety_stock
        )
    )
    cur_method = method
    cur_fr = achieved_fill_rate(working, cur_rop, max(cur_q, 1.0), cur_method)
    cur_csl = achieved_cycle_service_level(working, cur_rop, cur_method)

    rec_short = expected_shortage(mu, sigma, rec_rop, method)
    cur_short = expected_shortage(mu, sigma, cur_rop, cur_method)
    rec_cost = _annual_holding_cost(rec_ss, working) + _annual_shortage_cost(
        working, rec_short, max(qty, 1.0), DEFAULT_SHORTAGE_PENALTY_RATE
    )
    cur_cost = _annual_holding_cost(working.current_safety_stock, working) + _annual_shortage_cost(
        working, cur_short, max(cur_q, 1.0), DEFAULT_SHORTAGE_PENALTY_RATE
    )

    overdispersion = 0.0 if mu <= 0.0 else float(sigma**2 / mu)

    return PolicyRecommendation(
        sku_id=working.sku_id,
        location_id=working.location_id,
        demand_class=working.demand_class,
        method=method,
        demand_mean=working.demand_mean,
        demand_std=working.demand_std,
        lead_time_mean=working.lead_time_mean,
        lead_time_std=working.lead_time_std,
        sigma_dl=sigma,
        mu_dl=mu,
        z=z,
        safety_stock=float(rec_ss),
        reorder_point=float(rec_rop),
        order_quantity=float(qty),
        eoq_unrounded=float(eoq),
        target_service_level=float(target),
        service_level_kind=service_kind,
        achieved_fill_rate=rec_fr,
        achieved_csl=rec_csl,
        unit_cost=working.unit_cost,
        current_safety_stock=working.current_safety_stock,
        current_reorder_point=float(cur_rop),
        current_order_qty=float(cur_q),
        current_fill_rate=cur_fr,
        current_csl=cur_csl,
        safety_stock_delta_units=float(rec_ss - working.current_safety_stock),
        safety_stock_delta_dollars=float(
            (rec_ss - working.current_safety_stock) * working.unit_cost
        ),
        annual_net_benefit=float(cur_cost - rec_cost),
        overdispersion=overdispersion,
    )


def _rung_investment(rec: PolicyRecommendation) -> float:
    """Inventory investment used on the frontier: cycle stock + safety stock."""
    cycle = rec.order_quantity / 2.0
    return float((max(rec.safety_stock, 0.0) + cycle) * rec.unit_cost)


def _weighted_fill_rate(
    recs: list[PolicyRecommendation], params_by_key: dict[tuple[str, str], SkuLocationParams]
) -> float:
    num = 0.0
    den = 0.0
    for rec in recs:
        demand = params_by_key[(rec.sku_id, rec.location_id)].yearly_demand()
        num += rec.achieved_fill_rate * demand
        den += demand
    return float(num / den) if den > 0.0 else 1.0


def allocate_service_levels(
    items: list[SkuLocationParams],
    budget: float,
    *,
    service_grid: tuple[float, ...] = SERVICE_LEVEL_GRID,
) -> AllocationResult:
    """Greedy fill-rate-per-dollar allocation under an investment ceiling.

    For each SKU × location we precompute a ladder of policies on
    ``service_grid``. Every item starts at the cheapest rung. We then
    repeatedly buy the upgrade with the highest
    ``Δ(demand-weighted fill rate) / Δ$`` that still fits in the remaining
    budget.

    This equimarginal heuristic is near-optimal when fill rate is concave in
    safety stock (true for the normal, Poisson, and NB models used here) and
    is far easier to explain in a demo than a linear program.

    Assumption: cycle stock (EOQ/2) is independent of the service level, so
    the marginal dollar is almost entirely extra safety stock.
    """
    if not items:
        return AllocationResult(
            recommendations=(),
            investment=0.0,
            weighted_fill_rate=1.0,
            budget=float(budget),
            unallocated_budget=float(budget),
        )

    params_by_key = {(p.sku_id, p.location_id): p for p in items}
    ladders: list[list[PolicyRecommendation]] = []
    for item in items:
        rungs = [recommend_policy(item, target_service_level=level) for level in service_grid]
        ladders.append(rungs)

    index = [0] * len(items)
    remaining = float(budget)

    def current_recs() -> list[PolicyRecommendation]:
        return [ladders[i][index[i]] for i in range(len(items))]

    def total_investment(recs: list[PolicyRecommendation]) -> float:
        return float(sum(_rung_investment(r) for r in recs))

    # If the cheapest ladder already exceeds the budget, return it anyway —
    # the frontier caller can still plot the point. Remaining budget is 0.
    base_inv = total_investment(current_recs())
    if base_inv > remaining:
        recs = current_recs()
        return AllocationResult(
            recommendations=tuple(recs),
            investment=base_inv,
            weighted_fill_rate=_weighted_fill_rate(recs, params_by_key),
            budget=float(budget),
            unallocated_budget=0.0,
        )

    remaining -= base_inv
    upgraded = True
    while upgraded:
        upgraded = False
        best_i = -1
        best_score = -1.0
        best_cost = 0.0
        current = current_recs()
        current_fr = _weighted_fill_rate(current, params_by_key)
        for i, ladder in enumerate(ladders):
            nxt = index[i] + 1
            if nxt >= len(ladder):
                continue
            delta_dollars = _rung_investment(ladder[nxt]) - _rung_investment(ladder[index[i]])
            if delta_dollars <= 1e-9:
                # Free (or numerically tied) upgrade: take it.
                index[i] = nxt
                upgraded = True
                best_i = -1
                break
            if delta_dollars > remaining:
                continue
            trial = list(current)
            trial[i] = ladder[nxt]
            delta_fr = _weighted_fill_rate(trial, params_by_key) - current_fr
            score = delta_fr / delta_dollars
            if score > best_score:
                best_score = score
                best_i = i
                best_cost = delta_dollars
        if best_i >= 0:
            index[best_i] += 1
            remaining -= best_cost
            upgraded = True

    recs = current_recs()
    inv = total_investment(recs)
    return AllocationResult(
        recommendations=tuple(recs),
        investment=inv,
        weighted_fill_rate=_weighted_fill_rate(recs, params_by_key),
        budget=float(budget),
        unallocated_budget=float(max(budget - inv, 0.0)),
    )


def efficient_frontier(
    items: list[SkuLocationParams],
    *,
    service_grid: tuple[float, ...] = SERVICE_LEVEL_GRID,
) -> tuple[FrontierPoint, ...]:
    """Trace the greedy fill-rate vs investment curve from min to max service.

    Walks the same upgrades as :func:`allocate_service_levels` with an
    infinite budget and records (investment, weighted fill rate) after each
    step. The current-policy point is *not* on this curve — the UI should
    plot it separately so the gap is visible.
    """
    if not items:
        return (FrontierPoint(investment=0.0, weighted_fill_rate=1.0, n_upgrades=0),)

    params_by_key = {(p.sku_id, p.location_id): p for p in items}
    ladders = [
        [recommend_policy(item, target_service_level=level) for level in service_grid]
        for item in items
    ]
    index = [0] * len(items)
    points: list[FrontierPoint] = []

    def recs() -> list[PolicyRecommendation]:
        return [ladders[i][index[i]] for i in range(len(items))]

    def snapshot(n_upgrades: int) -> FrontierPoint:
        current = recs()
        inv = float(sum(_rung_investment(r) for r in current))
        return FrontierPoint(
            investment=inv,
            weighted_fill_rate=_weighted_fill_rate(current, params_by_key),
            n_upgrades=n_upgrades,
        )

    points.append(snapshot(0))
    n_upgrades = 0
    while True:
        current = recs()
        current_fr = _weighted_fill_rate(current, params_by_key)
        best_i = -1
        best_score = -1.0
        for i, ladder in enumerate(ladders):
            nxt = index[i] + 1
            if nxt >= len(ladder):
                continue
            delta_dollars = _rung_investment(ladder[nxt]) - _rung_investment(ladder[index[i]])
            trial = list(current)
            trial[i] = ladder[nxt]
            delta_fr = _weighted_fill_rate(trial, params_by_key) - current_fr
            score = delta_fr / delta_dollars if delta_dollars > 1e-9 else float("inf")
            if score > best_score:
                best_score = score
                best_i = i
        if best_i < 0:
            break
        index[best_i] += 1
        n_upgrades += 1
        points.append(snapshot(n_upgrades))

    return tuple(points)


def params_from_demand_history(
    sku_id: str,
    location_id: str,
    demand: np.ndarray | list[float] | tuple[float, ...],
    *,
    lead_time_mean: float,
    lead_time_std: float,
    unit_cost: float,
    **kwargs,
) -> SkuLocationParams:
    """Build :class:`SkuLocationParams` from a weekly demand history."""
    stats = demand_statistics(demand)
    return SkuLocationParams(
        sku_id=sku_id,
        location_id=location_id,
        demand_mean=stats.mean,
        demand_std=stats.std,
        demand_class=stats.demand_class,
        lead_time_mean=lead_time_mean,
        lead_time_std=lead_time_std,
        unit_cost=unit_cost,
        **kwargs,
    )
