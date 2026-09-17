"""What-if shocks against current vs recommended inventory policy.

Each shock is a pure transformation of :class:`SkuLocationParams`. Service
impact is then evaluated by holding a frozen (ROP, Q) policy against the
shocked lead-time-demand distribution — that is the point of the demo:
today's policy was sized for yesterday's lead time.

Shocks
------
* ``lead_time`` — one supplier's mean and std lead time are scaled
  (default ×2). Scaling both keeps the lead-time CV constant, which is the
  usual assumption when a carrier or factory simply "takes twice as long".
* ``region`` — every SKU sourced from a region is scaled the same way
  (a port / mill disruption).
* ``demand`` — a category's weekly mean and std are scaled (default ×1.20),
  i.e. a demand step-up that preserves CV.

Textbook framing: this is a comparative-static stress test, not a
stochastic simulation. We recompute ``sigma_DL`` and Type-II fill rate
under the shocked parameters; we do not resample demand paths.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from core.policy import (
    PolicyRecommendation,
    SkuLocationParams,
    achieved_cycle_service_level,
    achieved_fill_rate,
    recommend_policy,
)


@dataclass(frozen=True)
class Shock:
    """A named comparative-static shock.

    ``kind`` is one of ``lead_time``, ``region``, ``demand``.
    ``key`` is the supplier_id, sourcing_region, or category to match.
    ``multiplier`` scales the shocked fields (2.0 = double).
    """

    kind: str
    key: str
    multiplier: float = 2.0
    label: str = ""

    def describe(self) -> str:
        if self.label:
            return self.label
        if self.kind == "lead_time":
            return f"Supplier {self.key} lead time ×{self.multiplier:g}"
        if self.kind == "region":
            return f"Sourcing region {self.key} disrupted (lead time ×{self.multiplier:g})"
        if self.kind == "demand":
            pct = (self.multiplier - 1.0) * 100.0
            return f"Category {self.key} demand {pct:+.0f}%"
        return f"{self.kind}:{self.key}×{self.multiplier:g}"


@dataclass(frozen=True)
class PolicySnapshot:
    """A frozen (ROP, Q) policy evaluated under some demand/LT regime."""

    reorder_point: float
    order_quantity: float
    safety_stock: float
    fill_rate: float
    cycle_service_level: float
    method: str


@dataclass(frozen=True)
class SkuShockResult:
    sku_id: str
    location_id: str
    demand_class: str
    method: str
    shocked: bool
    baseline_fill_rate_current: float
    shocked_fill_rate_current: float
    baseline_fill_rate_recommended: float
    shocked_fill_rate_recommended: float
    reoptimized_fill_rate: float
    fill_rate_gap_current: float
    fill_rate_gap_recommended: float


@dataclass(frozen=True)
class ScenarioComparison:
    shock: Shock
    n_items: int
    n_shocked: int
    current_fill_rate_baseline: float
    current_fill_rate_shocked: float
    recommended_fill_rate_baseline: float
    recommended_fill_rate_shocked: float
    reoptimized_fill_rate: float
    rows: tuple[SkuShockResult, ...]


def apply_shock(item: SkuLocationParams, shock: Shock) -> SkuLocationParams:
    """Return a copy of ``item`` with the shock applied, or the original.

    Lead-time shocks scale ``lead_time_mean`` and ``lead_time_std``.
    Demand shocks scale ``demand_mean`` and ``demand_std`` (and annual
    demand if it was set explicitly). Unmatched items are returned
    unchanged so a catalog can be mapped in one pass.
    """
    kind = shock.kind
    key = shock.key
    m = float(shock.multiplier)
    if kind == "lead_time":
        if item.supplier_id != key:
            return item
        return replace(
            item,
            lead_time_mean=item.lead_time_mean * m,
            lead_time_std=item.lead_time_std * m,
        )
    if kind == "region":
        if item.sourcing_region != key:
            return item
        return replace(
            item,
            lead_time_mean=item.lead_time_mean * m,
            lead_time_std=item.lead_time_std * m,
        )
    if kind == "demand":
        if item.category != key:
            return item
        annual = None if item.annual_demand is None else item.annual_demand * m
        return replace(
            item,
            demand_mean=item.demand_mean * m,
            demand_std=item.demand_std * m,
            annual_demand=annual,
        )
    raise ValueError(f"unknown shock kind {kind!r}; expected lead_time, region, or demand")


def _evaluate(
    item: SkuLocationParams,
    reorder_point: float,
    order_qty: float,
    method: str,
) -> PolicySnapshot:
    q = order_qty if order_qty > 0.0 else 1.0
    return PolicySnapshot(
        reorder_point=float(reorder_point),
        order_quantity=float(order_qty),
        safety_stock=float(reorder_point - item.demand_mean * item.lead_time_mean),
        fill_rate=achieved_fill_rate(item, reorder_point, q, method),
        cycle_service_level=achieved_cycle_service_level(item, reorder_point, method),
        method=method,
    )


def _weighted_fr(pairs: list[tuple[SkuLocationParams, float]]) -> float:
    num = 0.0
    den = 0.0
    for item, fr in pairs:
        d = item.yearly_demand()
        num += fr * d
        den += d
    return float(num / den) if den > 0.0 else 1.0


def compare_policies_under_shock(
    items: list[SkuLocationParams],
    shock: Shock,
    *,
    recommendations: list[PolicyRecommendation] | None = None,
    target_service_level: float | None = None,
) -> ScenarioComparison:
    """Service under current vs recommended policy, before and after a shock.

    For each SKU × location we report three fill rates on the *shocked*
    demand/lead-time regime:

    1. Current (ROP, Q) held fixed — typically collapses when lead time doubles.
    2. Recommended (ROP, Q) held fixed — still sized on the old regime, but
       usually more robust because it already priced lead-time variance.
    3. Re-optimized policy on the shocked parameters — the ceiling.

    Demand-weighted averages sit on :class:`ScenarioComparison` for the
    scenario-planner headline tiles.
    """
    rec_map: dict[tuple[str, str], PolicyRecommendation] = {}
    if recommendations is not None:
        rec_map = {(r.sku_id, r.location_id): r for r in recommendations}

    rows: list[SkuShockResult] = []
    cur_base: list[tuple[SkuLocationParams, float]] = []
    cur_shock: list[tuple[SkuLocationParams, float]] = []
    rec_base: list[tuple[SkuLocationParams, float]] = []
    rec_shock: list[tuple[SkuLocationParams, float]] = []
    reopt: list[tuple[SkuLocationParams, float]] = []
    n_shocked = 0

    for item in items:
        rec = rec_map.get((item.sku_id, item.location_id))
        if rec is None:
            rec = recommend_policy(item, target_service_level=target_service_level)
        shocked_item = apply_shock(item, shock)
        was_shocked = shocked_item is not item and shocked_item != item
        if was_shocked:
            n_shocked += 1

        method = rec.method
        cur_q = item.current_order_qty if item.current_order_qty > 0 else rec.order_quantity
        cur_rop = (
            item.current_reorder_point
            if item.current_reorder_point > 0
            else rec.current_reorder_point
        )

        base_cur = _evaluate(item, cur_rop, cur_q, method)
        shock_cur = _evaluate(shocked_item, cur_rop, cur_q, method)
        base_rec = _evaluate(item, rec.reorder_point, rec.order_quantity, method)
        shock_rec = _evaluate(shocked_item, rec.reorder_point, rec.order_quantity, method)
        reopt_rec = recommend_policy(shocked_item, target_service_level=target_service_level)

        rows.append(
            SkuShockResult(
                sku_id=item.sku_id,
                location_id=item.location_id,
                demand_class=rec.demand_class,
                method=method,
                shocked=was_shocked,
                baseline_fill_rate_current=base_cur.fill_rate,
                shocked_fill_rate_current=shock_cur.fill_rate,
                baseline_fill_rate_recommended=base_rec.fill_rate,
                shocked_fill_rate_recommended=shock_rec.fill_rate,
                reoptimized_fill_rate=reopt_rec.achieved_fill_rate,
                fill_rate_gap_current=shock_cur.fill_rate - base_cur.fill_rate,
                fill_rate_gap_recommended=shock_rec.fill_rate - base_rec.fill_rate,
            )
        )
        cur_base.append((item, base_cur.fill_rate))
        cur_shock.append((shocked_item, shock_cur.fill_rate))
        rec_base.append((item, base_rec.fill_rate))
        rec_shock.append((shocked_item, shock_rec.fill_rate))
        reopt.append((shocked_item, reopt_rec.achieved_fill_rate))

    return ScenarioComparison(
        shock=shock,
        n_items=len(items),
        n_shocked=n_shocked,
        current_fill_rate_baseline=_weighted_fr(cur_base),
        current_fill_rate_shocked=_weighted_fr(cur_shock),
        recommended_fill_rate_baseline=_weighted_fr(rec_base),
        recommended_fill_rate_shocked=_weighted_fr(rec_shock),
        reoptimized_fill_rate=_weighted_fr(reopt),
        rows=tuple(rows),
    )
