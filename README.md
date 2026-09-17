# Meridian Industrial Supply

A fully synthetic dbt and Snowflake teaching project for inventory and supply-chain optimization at a fictional national MRO distributor. No source record refers to a real company, supplier, brand, or customer.

## Project layers

- `seeds/` simulates ERP and WMS landing tables.
- `models/staging/` standardizes source types and identifiers without business logic.
- `models/intermediate/` defines reusable demand, inventory, lead-time, substitution, and stockout logic.
- `models/marts/supply_chain/` publishes dimensional, fact, and optimizer-ready aggregate tables.
- `models/semantic/` governs shared metrics and dashboard query shapes.

## Streamlit optimizer data access

The Streamlit app uses the **dbt Semantic Layer GraphQL API** for business metrics that must remain consistent across the app and BI tools:

- net sales, cost of goods, gross margin, and gross margin percent
- line and unit fill rates, backorder rate, and substitution rate
- gross demand and trailing 12-week gross demand
- period-end on-hand and on-order value
- stockout days and demand affected by stockouts
- supplier on-time rate and open purchase-order value
- inventory turns, days of supply, GMROI, and excess/obsolete inventory value

These calculations belong in the Semantic Layer because their aggregation, filters, entity joins, and semi-additive inventory behavior must be governed centrally. In particular, inventory metrics select the latest snapshot in a requested period instead of summing balances through time.

The optimizer reads **row-level feature inputs directly from marts** when it needs a dense dataset rather than an aggregated business metric:

- `agg_sku_location_demand_weekly` for zero-filled weekly demand history, variability, current policy settings, and lead-time distributions
- `fct_inventory_snapshots` for point-in-time SKU-location balances used in simulations
- `dim_products` and `dim_locations` for item constraints and network topology

Direct mart reads keep high-volume feature extraction efficient and preserve the row grain required by optimization algorithms. The app should not reimplement governed KPI formulas over those rows; displayed KPIs come back through GraphQL.

## Validation

```bash
dbt build
dbt sl validate
dbt sl query --metrics net_sales,line_fill_rate --group-by metric_time__month
```
