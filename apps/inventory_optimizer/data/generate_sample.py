"""Build the offline parquet fixture used by ``streamlit run app.py -- --sample``.

The catalog reuses Meridian's fictional SKU, supplier, and location identifiers
so the sample mode looks like the warehouse. Demand paths are generated, not
copied from seeds, so the optimizer has enough history to classify all four
Syntetos-Boylan quadrants.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from core.demand import demand_statistics
from core.policy import z_from_service_level

SAMPLE_DIR = Path(__file__).resolve().parent / "sample"
N_WEEKS = 52
END_WEEK = pd.Timestamp("2026-09-14")  # Monday


PRODUCTS = [
    {"sku": "SKU000001", "product_name": "Cut Resistant Gloves", "category": "safety_ppe", "abc_class": "A", "unit_cost": 8.50, "supplier_id": "SUP0001", "min_order_qty": 12, "order_multiple": 12, "pattern": "smooth"},
    {"sku": "SKU000002", "product_name": "Protective Safety Glasses", "category": "safety_ppe", "abc_class": "A", "unit_cost": 5.25, "supplier_id": "SUP0001", "min_order_qty": 24, "order_multiple": 12, "pattern": "erratic"},
    {"sku": "SKU000003", "product_name": "Ice Control Pellets", "category": "winter", "abc_class": "B", "unit_cost": 18.75, "supplier_id": "SUP0002", "min_order_qty": 10, "order_multiple": 5, "pattern": "lumpy"},
    {"sku": "SKU000004", "product_name": "Pleated Air Filter", "category": "hvac_filters", "abc_class": "A", "unit_cost": 32.00, "supplier_id": "SUP0001", "min_order_qty": 12, "order_multiple": 12, "pattern": "smooth"},
    {"sku": "SKU000005", "product_name": "Portable Cooling Fan", "category": "cooling", "abc_class": "B", "unit_cost": 74.50, "supplier_id": "SUP0004", "min_order_qty": 2, "order_multiple": 1, "pattern": "seasonal"},
    {"sku": "SKU000006", "product_name": "Hex Bolt Assortment", "category": "fasteners", "abc_class": "A", "unit_cost": 11.25, "supplier_id": "SUP0001", "min_order_qty": 10, "order_multiple": 10, "pattern": "smooth"},
    {"sku": "SKU000007", "product_name": "Industrial Bearing", "category": "power_transmission", "abc_class": "C", "unit_cost": 42.75, "supplier_id": "SUP0003", "min_order_qty": 5, "order_multiple": 5, "pattern": "intermittent"},
    {"sku": "SKU000008", "product_name": "Hydraulic Hose", "category": "fluid_handling", "abc_class": "C", "unit_cost": 58.00, "supplier_id": "SUP0003", "min_order_qty": 2, "order_multiple": 2, "pattern": "lumpy"},
    {"sku": "SKU000009", "product_name": "Precision Caliper", "category": "tools", "abc_class": "B", "unit_cost": 36.50, "supplier_id": "SUP0002", "min_order_qty": 2, "order_multiple": 1, "pattern": "erratic"},
    {"sku": "SKU000010", "product_name": "Legacy Drive Belt", "category": "power_transmission", "abc_class": "C", "unit_cost": 21.00, "supplier_id": "SUP0004", "min_order_qty": 5, "order_multiple": 5, "pattern": "intermittent"},
]

LOCATIONS = [
    {"location_id": "LOC001", "location_name": "Meridian National DC 01", "location_type": "national_dc", "echelon_level": 0, "region": "central", "parent_location_id": None},
    {"location_id": "LOC002", "location_name": "Meridian Regional DC 02", "location_type": "regional_dc", "echelon_level": 1, "region": "central", "parent_location_id": "LOC001"},
    {"location_id": "LOC003", "location_name": "Meridian Branch Pittsburgh", "location_type": "branch", "echelon_level": 2, "region": "northeast", "parent_location_id": "LOC002"},
    {"location_id": "LOC005", "location_name": "Meridian Branch Cleveland", "location_type": "branch", "echelon_level": 2, "region": "central", "parent_location_id": "LOC002"},
    {"location_id": "LOC006", "location_name": "Meridian Branch Indianapolis", "location_type": "branch", "echelon_level": 2, "region": "central", "parent_location_id": "LOC002"},
]

SUPPLIERS = [
    {"supplier_id": "SUP0001", "supplier_name": "Fictional Supply Partner 001", "sourcing_region": "north_america", "mean_actual_lead_time_days": 7.0, "stddev_actual_lead_time_days": 1.2, "supplier_on_time_rate": 0.96, "po_line_count": 180, "open_po_value": 42000.0, "is_reliable_sample": True},
    {"supplier_id": "SUP0002", "supplier_name": "Fictional Supply Partner 002", "sourcing_region": "eastern_corridor", "mean_actual_lead_time_days": 24.0, "stddev_actual_lead_time_days": 8.5, "supplier_on_time_rate": 0.81, "po_line_count": 95, "open_po_value": 61000.0, "is_reliable_sample": True},
    {"supplier_id": "SUP0003", "supplier_name": "Fictional Supply Partner 003", "sourcing_region": "pacific_basin", "mean_actual_lead_time_days": 42.0, "stddev_actual_lead_time_days": 18.0, "supplier_on_time_rate": 0.62, "po_line_count": 70, "open_po_value": 88000.0, "is_reliable_sample": True},
    {"supplier_id": "SUP0004", "supplier_name": "Fictional Supply Partner 004", "sourcing_region": "central_europe", "mean_actual_lead_time_days": 30.0, "stddev_actual_lead_time_days": 6.0, "supplier_on_time_rate": 0.88, "po_line_count": 64, "open_po_value": 27500.0, "is_reliable_sample": True},
]


def _weeks() -> pd.DatetimeIndex:
    return pd.date_range(end=END_WEEK, periods=N_WEEKS, freq="W-MON")


def _series(pattern: str, n: int, rng: np.random.Generator) -> np.ndarray:
    t = np.arange(n)
    if pattern == "smooth":
        return np.clip(rng.normal(28.0, 3.5, n), 8.0, None).round()
    if pattern == "erratic":
        low = rng.integers(2, 6, n)
        high = rng.integers(22, 40, n)
        return np.where(t % 2 == 0, low, high).astype(float)
    if pattern == "intermittent":
        hits = rng.choice([0.0, 8.0, 10.0], size=n, p=[0.72, 0.18, 0.10])
        return hits
    if pattern == "lumpy":
        qty = np.zeros(n)
        for i in range(n):
            if rng.random() < 0.18:
                qty[i] = float(rng.choice([4, 6, 28, 45, 60]))
        return qty
    if pattern == "seasonal":
        # Cooling fans: summer bump around week 20-32 of a Sep-ending year (prior winter/spring/summer).
        seasonal = 8 + 18 * np.exp(-0.5 * ((t - 34) / 6.0) ** 2)
        return np.clip(rng.normal(seasonal, 3.0), 0, None).round()
    raise ValueError(pattern)


def _naive_policy(mean: float, std: float, lead_weeks: float, z: float) -> tuple[float, float, float]:
    """Intentionally naive current policy: z * sigma_d * sqrt(L), no LT variance."""
    ss = max(z * std * np.sqrt(max(lead_weeks, 0.0)), 0.0)
    rop = mean * lead_weeks + ss
    q = max(round(mean * 4.0), 1.0)
    return float(ss), float(rop), float(q)


def build_frames(seed: int = 7) -> dict[str, pd.DataFrame]:
    rng = np.random.default_rng(seed)
    weeks = _weeks()
    z = z_from_service_level(0.95)
    suppliers = {row["supplier_id"]: row for row in SUPPLIERS}
    loc_scale = {"LOC001": 1.8, "LOC002": 1.2, "LOC003": 0.7, "LOC005": 0.65, "LOC006": 0.6}

    weekly_rows: list[dict] = []
    for product in PRODUCTS:
        supplier = suppliers[product["supplier_id"]]
        lead_days = supplier["mean_actual_lead_time_days"]
        lead_std_days = supplier["stddev_actual_lead_time_days"]
        lead_weeks = lead_days / 7.0
        lead_std_weeks = lead_std_days / 7.0
        for loc in LOCATIONS:
            # Keep C items off the national DC to leave a branch-heavy pooling story.
            if product["abc_class"] == "C" and loc["location_type"] == "national_dc":
                continue
            base = _series(product["pattern"], N_WEEKS, rng)
            demand = np.clip((base * loc_scale[loc["location_id"]]).round(), 0, None)
            stats = demand_statistics(demand)
            ss, rop, q = _naive_policy(stats.mean, stats.std, lead_weeks, z)
            fill = float(np.clip(0.97 - 0.12 * (lead_std_weeks / max(lead_weeks, 0.1)), 0.55, 0.99))
            for week, qty in zip(weeks, demand):
                shipped = float(min(qty, np.round(qty * fill)))
                weekly_rows.append(
                    {
                        "sku": product["sku"],
                        "product_name": product["product_name"],
                        "location_id": loc["location_id"],
                        "location_name": loc["location_name"],
                        "location_type": loc["location_type"],
                        "echelon_level": loc["echelon_level"],
                        "region": loc["region"],
                        "parent_location_id": loc["parent_location_id"],
                        "demand_week": week,
                        "category": product["category"],
                        "abc_class": product["abc_class"],
                        "gross_demand_qty": float(qty),
                        "net_shipped_qty": shipped,
                        "backordered_qty": float(qty - shipped),
                        "substituted_qty": 0.0,
                        "order_line_count": int(qty > 0),
                        "shipped_line_count": int(qty > 0 and shipped >= qty),
                        "mean_weekly_demand": stats.mean,
                        "stddev_weekly_demand": stats.std,
                        "coefficient_of_variation": stats.cv if np.isfinite(stats.cv) else None,
                        "average_demand_interval": stats.adi if np.isfinite(stats.adi) else None,
                        "demand_class": stats.demand_class,
                        "current_safety_stock_qty": ss,
                        "current_reorder_point": rop,
                        "current_reorder_qty": q,
                        "primary_supplier_id": product["supplier_id"],
                        "mean_lead_time_days": lead_days,
                        "stddev_lead_time_days": lead_std_days,
                        "is_reliable_lead_time_sample": True,
                        "min_order_qty": product["min_order_qty"],
                        "order_multiple": product["order_multiple"],
                        "unit_cost": product["unit_cost"],
                        "sourcing_region": supplier["sourcing_region"],
                    }
                )

    weekly = pd.DataFrame(weekly_rows)
    latest = (
        weekly.sort_values("demand_week")
        .groupby(["sku", "location_id"], as_index=False)
        .tail(1)
        .copy()
    )
    latest["on_hand_value"] = (
        (latest["current_safety_stock_qty"] + latest["current_reorder_qty"] / 2.0) * latest["unit_cost"]
    )
    latest["on_order_value"] = latest["current_reorder_qty"] * 0.35 * latest["unit_cost"]
    latest["excess_obsolete_on_hand_value"] = np.where(
        latest["demand_class"].eq("intermittent") & latest["abc_class"].eq("C"),
        latest["unit_cost"] * 40.0,
        0.0,
    )
    inventory_by_echelon = latest.groupby(["location_type", "abc_class"], as_index=False).agg(
        on_hand_value=("on_hand_value", "sum"),
        on_order_value=("on_order_value", "sum"),
        excess_obsolete_on_hand_value=("excess_obsolete_on_hand_value", "sum"),
    )

    fill_trend = (
        weekly.assign(month=weekly["demand_week"].dt.to_period("M").dt.to_timestamp())
        .groupby("month", as_index=False)
        .agg(
            weekly_shipped_line_count=("shipped_line_count", "sum"),
            weekly_order_line_count=("order_line_count", "sum"),
            gross_demand_units=("gross_demand_qty", "sum"),
        )
    )
    fill_trend["weekly_line_fill_rate"] = (
        fill_trend["weekly_shipped_line_count"] / fill_trend["weekly_order_line_count"].replace(0, np.nan)
    )

    stockouts = (
        latest.assign(
            stockout_days=np.where(latest["demand_class"].isin(["lumpy", "intermittent"]), 18, 4),
            stockout_impact_units=latest["mean_weekly_demand"] * np.where(latest["demand_class"].isin(["lumpy", "intermittent"]), 3.0, 0.4),
        )
        .groupby(["sku", "product_name", "category"], as_index=False)
        .agg(stockout_days=("stockout_days", "sum"), stockout_impact_units=("stockout_impact_units", "sum"))
        .sort_values("stockout_impact_units", ascending=False)
        .head(8)
    )

    kpis = pd.DataFrame(
        [
            {"metric": "on_hand_value", "value": float(((latest["current_safety_stock_qty"] + latest["current_reorder_qty"] / 2) * latest["unit_cost"]).sum())},
            {"metric": "line_fill_rate", "value": float(weekly["shipped_line_count"].sum() / max(weekly["order_line_count"].sum(), 1))},
            {"metric": "unit_fill_rate", "value": float(weekly["net_shipped_qty"].sum() / max(weekly["gross_demand_qty"].sum(), 1))},
            {"metric": "stockout_impact_units", "value": float(stockouts["stockout_impact_units"].sum())},
            {"metric": "supplier_on_time_rate", "value": float(np.mean([s["supplier_on_time_rate"] for s in SUPPLIERS]))},
            {"metric": "gross_demand_units", "value": float(weekly["gross_demand_qty"].sum())},
        ]
    )

    return {
        "weekly_demand": weekly,
        "supplier_scorecard": pd.DataFrame(SUPPLIERS),
        "locations": pd.DataFrame(LOCATIONS),
        "inventory_by_echelon_abc": inventory_by_echelon,
        "fill_rate_trend": fill_trend,
        "top_stockout_impact": stockouts,
        "headline_kpis": kpis,
    }


def write_sample(directory: Path | None = None) -> Path:
    directory = directory or SAMPLE_DIR
    directory.mkdir(parents=True, exist_ok=True)
    frames = build_frames()
    for name, frame in frames.items():
        frame.to_parquet(directory / f"{name}.parquet", index=False)
    return directory


if __name__ == "__main__":
    path = write_sample()
    print(f"wrote sample fixtures to {path}")
