# Meridian Industrial Supply — Inventory Policy Optimizer

Local Streamlit app for multi-echelon inventory policy on top of the `meridian_supply_chain` dbt project. The distributor is fictional.

## Run without a warehouse

```bash
cd apps/inventory_optimizer
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py -- --sample
```

`--sample` loads parquet fixtures under `data/sample/` so the five pages work offline.

## Run against Snowflake + the Semantic Layer

Copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and fill in placeholders. Then:

```bash
streamlit run app.py
```

Network overview KPIs come from the dbt Semantic Layer GraphQL API (`on_hand_value`, `line_fill_rate`, `weekly_line_fill_rate`, `stockout_impact_units`, …). SKU × location math reads `agg_sku_location_demand_weekly` and `agg_supplier_scorecard`.

Writeback creates `policy_recommendations` in the configured schema and inserts a stamped run. dbt then compares those rows to later inventory snapshots in `fct_policy_recommendation_impact`.

## Tests

```bash
cd apps/inventory_optimizer
pytest
```

No Snowflake required. Demand classification is tested against the same fixtures as `int_demand_variability`.

## Math (short)

```
sigma_DL = sqrt(L * sigma_d^2 + d_bar^2 * sigma_L^2)
SS       = z * sigma_DL          # smooth / erratic
```

Intermittent and lumpy SKUs use Poisson or negative-binomial fill-rate sizing. Method is shown per SKU. EOQ is Harris/Wilson, rounded to MOQ and order multiple. Pooling is the square-root law. Budgeted service is greedy fill-rate-per-dollar — no solver framework.
