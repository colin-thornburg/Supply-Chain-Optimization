"""Snowflake + Semantic Layer access, with a local parquet fallback.

Headline KPIs come from the dbt Semantic Layer GraphQL API so the app's
numbers match governed metric definitions. SKU × location detail used by the
optimizer is read from ``agg_sku_location_demand_weekly`` and
``agg_supplier_scorecard`` via snowflake-connector-python.

Credentials are read from ``st.secrets`` only. Cache TTL is 10 minutes.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pandas as pd

from core.demand import demand_statistics
from core.policy import SkuLocationParams

SAMPLE_DIR = Path(__file__).resolve().parent / "sample"
CACHE_TTL_SECONDS = 10 * 60


def is_sample_mode() -> bool:
    if "--sample" in sys.argv:
        return True
    return os.environ.get("INVENTORY_OPTIMIZER_SAMPLE", "").lower() in {"1", "true", "yes"}


def _streamlit():
    import streamlit as st

    return st


def _cached(fn):
    st = _streamlit()
    return st.cache_data(ttl=CACHE_TTL_SECONDS, show_spinner=False)(fn)


@dataclass(frozen=True)
class SnowflakeSettings:
    account: str
    user: str
    password: str
    warehouse: str
    role: str
    database: str
    schema: str


@dataclass(frozen=True)
class SemanticLayerSettings:
    host: str
    environment_id: str
    token: str


def snowflake_settings() -> SnowflakeSettings:
    secrets = _streamlit().secrets["snowflake"]
    return SnowflakeSettings(
        account=str(secrets["account"]),
        user=str(secrets["user"]),
        password=str(secrets["password"]),
        warehouse=str(secrets.get("warehouse", "TRANSFORMING")),
        role=str(secrets.get("role", "TRANSFORMER")),
        database=str(secrets.get("database", "MERIDIAN_SUPPLY_CHAIN")),
        schema=str(secrets.get("schema", "MARTS")),
    )


def semantic_layer_settings() -> SemanticLayerSettings:
    secrets = _streamlit().secrets["semantic_layer"]
    return SemanticLayerSettings(
        host=str(secrets["host"]).rstrip("/"),
        environment_id=str(secrets["environment_id"]),
        token=str(secrets["token"]),
    )


def _connect(settings: SnowflakeSettings):
    import snowflake.connector

    return snowflake.connector.connect(
        account=settings.account,
        user=settings.user,
        password=settings.password,
        warehouse=settings.warehouse,
        role=settings.role,
        database=settings.database,
        schema=settings.schema,
    )


def _read_sql(sql: str, settings: SnowflakeSettings) -> pd.DataFrame:
    with _connect(settings) as conn:
        return pd.read_sql(sql, conn)


def _fq(settings: SnowflakeSettings, relation: str) -> str:
    return f"{settings.database}.{settings.schema}.{relation}"


def _sample_frame(name: str) -> pd.DataFrame:
    path = SAMPLE_DIR / f"{name}.parquet"
    if not path.exists():
        from data.generate_sample import write_sample

        write_sample(SAMPLE_DIR)
    return pd.read_parquet(path)


@_cached
def load_weekly_demand(sample: bool = False) -> pd.DataFrame:
    """SKU × location × week feature table for the optimizer math."""
    if sample:
        weekly = _sample_frame("weekly_demand")
        weekly["demand_week"] = pd.to_datetime(weekly["demand_week"])
        return weekly
    settings = snowflake_settings()
    weekly = _read_sql(
        f"""
        select
            d.sku,
            d.location_id,
            d.demand_week,
            d.category,
            d.abc_class,
            d.gross_demand_qty,
            d.net_shipped_qty,
            d.backordered_qty,
            d.substituted_qty,
            d.order_line_count,
            d.shipped_line_count,
            d.mean_weekly_demand,
            d.stddev_weekly_demand,
            d.coefficient_of_variation,
            d.average_demand_interval,
            d.demand_class,
            d.current_safety_stock_qty,
            d.current_reorder_point,
            d.current_reorder_qty,
            d.primary_supplier_id,
            d.mean_lead_time_days,
            d.stddev_lead_time_days,
            d.is_reliable_lead_time_sample,
            l.location_name,
            l.location_type,
            l.echelon_level,
            l.region,
            l.parent_location_id,
            p.product_name,
            p.standard_unit_cost as unit_cost,
            s.sourcing_region,
            sp.min_order_qty,
            sp.order_multiple
        from {_fq(settings, "agg_sku_location_demand_weekly")} as d
        left join {_fq(settings, "dim_locations")} as l using (location_id)
        left join {_fq(settings, "dim_products")} as p using (sku)
        left join {_fq(settings, "dim_suppliers")} as s
            on d.primary_supplier_id = s.supplier_id
        left join {_fq(settings, "stg_erp__supplier_products")} as sp
            on d.sku = sp.sku
            and d.primary_supplier_id = sp.supplier_id
            and sp.is_primary_source
        """,
        settings,
    )
    weekly.columns = [c.lower() for c in weekly.columns]
    weekly["demand_week"] = pd.to_datetime(weekly["demand_week"])
    return weekly


@_cached
def load_supplier_scorecard(sample: bool = False) -> pd.DataFrame:
    if sample:
        return _sample_frame("supplier_scorecard")
    settings = snowflake_settings()
    scorecard = _read_sql(f"select * from {_fq(settings, 'agg_supplier_scorecard')}", settings)
    scorecard.columns = [c.lower() for c in scorecard.columns]
    suppliers = _read_sql(
        f"select supplier_id, supplier_name, sourcing_region from {_fq(settings, 'dim_suppliers')}",
        settings,
    )
    suppliers.columns = [c.lower() for c in suppliers.columns]
    return scorecard.merge(suppliers, on="supplier_id", how="left")


@_cached
def load_locations(sample: bool = False) -> pd.DataFrame:
    if sample:
        return _sample_frame("locations")
    settings = snowflake_settings()
    locations = _read_sql(
        f"""
        select location_id, location_name, location_type, echelon_level, region, parent_location_id
        from {_fq(settings, "dim_locations")}
        """,
        settings,
    )
    locations.columns = [c.lower() for c in locations.columns]
    return locations


def _graphql(settings: SemanticLayerSettings, query: str, variables: dict[str, Any]) -> dict[str, Any]:
    import urllib.error
    import urllib.request

    payload = json.dumps({"query": query, "variables": variables}).encode("utf-8")
    request = urllib.request.Request(
        f"{settings.host}/api/graphql",
        data=payload,
        headers={
            "Authorization": f"Bearer {settings.token}",
            "Content-Type": "application/json",
            "X-dbt-partner-source": "streamlit",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=60) as response:
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8")
        raise RuntimeError(f"Semantic Layer HTTP {exc.code}: {body}") from exc


METRICFLOW_QUERY = """
query MetricQuery($environmentId: BigInt!, $metrics: [MetricInput!]!, $groupBy: [GroupByInput!]) {
  metricflowQuery(
    environmentId: $environmentId
    metrics: $metrics
    groupBy: $groupBy
  ) {
    jsonResult
  }
}
"""


@_cached
def query_semantic_layer(
    metrics: tuple[str, ...],
    group_by: tuple[str, ...] = (),
    sample: bool = False,
    sample_name: str | None = None,
) -> pd.DataFrame:
    """Run a governed metric query. ``sample_name`` selects a parquet fixture."""
    if sample:
        if sample_name is None:
            raise ValueError("sample_name is required in sample mode")
        frame = _sample_frame(sample_name)
        return frame
    settings = semantic_layer_settings()
    variables = {
        "environmentId": int(settings.environment_id),
        "metrics": [{"name": name} for name in metrics],
        "groupBy": [{"name": name} for name in group_by],
    }
    payload = _graphql(settings, METRICFLOW_QUERY, variables)
    if payload.get("errors"):
        raise RuntimeError(payload["errors"])
    raw = payload["data"]["metricflowQuery"]["jsonResult"]
    rows = json.loads(raw) if isinstance(raw, str) else raw
    if isinstance(rows, dict) and "data" in rows:
        rows = rows["data"]
    return pd.DataFrame(rows)


@_cached
def load_headline_kpis(sample: bool = False) -> pd.DataFrame:
    if sample:
        return _sample_frame("headline_kpis")
    frames = []
    for metric in (
        "on_hand_value",
        "line_fill_rate",
        "unit_fill_rate",
        "stockout_impact_units",
        "supplier_on_time_rate",
        "gross_demand_units",
    ):
        try:
            frame = query_semantic_layer((metric,), sample=False)
            value_col = metric if metric in frame.columns else frame.columns[-1]
            frames.append({"metric": metric, "value": float(frame[value_col].iloc[0])})
        except Exception as exc:  # pragma: no cover - warehouse path
            frames.append({"metric": metric, "value": None, "error": str(exc)})
    return pd.DataFrame(frames)


def sku_location_params(weekly: pd.DataFrame) -> list[SkuLocationParams]:
    """Collapse weekly history into one :class:`SkuLocationParams` per SKU × location."""
    items: list[SkuLocationParams] = []
    grouped = weekly.sort_values("demand_week").groupby(["sku", "location_id"], sort=False)
    for (sku, location_id), group in grouped:
        latest = group.iloc[-1]
        stats = demand_statistics(group["gross_demand_qty"].to_numpy())
        lead_weeks = float(latest["mean_lead_time_days"]) / 7.0
        lead_std_weeks = float(latest["stddev_lead_time_days"]) / 7.0
        items.append(
            SkuLocationParams(
                sku_id=str(sku),
                location_id=str(location_id),
                demand_mean=stats.mean,
                demand_std=stats.std,
                demand_class=str(latest.get("demand_class") or stats.demand_class),
                lead_time_mean=lead_weeks,
                lead_time_std=lead_std_weeks,
                unit_cost=float(latest["unit_cost"]),
                target_service_level=0.95,
                min_order_qty=float(latest.get("min_order_qty") or 1.0),
                order_multiple=float(latest.get("order_multiple") or 1.0),
                order_cost=50.0,
                current_safety_stock=float(latest.get("current_safety_stock_qty") or 0.0),
                current_reorder_point=float(latest.get("current_reorder_point") or 0.0),
                current_order_qty=float(latest.get("current_reorder_qty") or 0.0),
                category=str(latest.get("category") or ""),
                supplier_id=str(latest.get("primary_supplier_id") or ""),
                sourcing_region=str(latest.get("sourcing_region") or ""),
                echelon=str(latest.get("location_type") or ""),
                region_id=str(latest.get("region") or ""),
                abc_class=str(latest.get("abc_class") or ""),
            )
        )
    return items


def write_recommendations_to_snowflake(frame: pd.DataFrame, ddl: str) -> int:
    """Create ``policy_recommendations`` if needed and insert the stamped rows."""
    settings = snowflake_settings()
    import snowflake.connector.pandas_tools as pandas_tools

    with _connect(settings) as conn:
        with conn.cursor() as cursor:
            cursor.execute(ddl)
        success, nchunks, nrows, _ = pandas_tools.write_pandas(
            conn,
            frame,
            "POLICY_RECOMMENDATIONS",
            database=settings.database,
            schema=settings.schema,
            auto_create_table=False,
            quote_identifiers=False,
        )
        if not success:
            raise RuntimeError(f"write_pandas failed after {nchunks} chunks")
        return int(nrows)
