{% docs demand_classification %}
Demand behavior follows the Syntetos-Boylan framework. Average demand interval (ADI) separates frequent demand at 1.32 weeks, while squared coefficient of variation separates stable demand at 0.49. The four mutually exclusive classes are smooth, erratic, intermittent, and lumpy.
{% enddocs %}

{% docs safety_stock %}
Safety stock is inventory held above expected cycle demand to absorb uncertainty in demand and replenishment lead time. Meridian's seeded policy is intentionally naive so the optimizer can compare a variability-aware recommendation with the current baseline.
{% enddocs %}

{% docs reorder_point %}
The reorder point is the inventory position at which replenishment should begin. A robust policy covers expected demand over replenishment lead time plus safety stock.
{% enddocs %}

{% docs fill_rate %}
Line fill rate is the share of order lines shipped completely. Unit fill rate is the share of requested units shipped. Both use uncensored ordered demand as the denominator so stockouts remain visible.
{% enddocs %}

{% docs days_of_supply %}
Days of supply estimates how long current on-hand units would last at the observed demand rate. Zero-demand items return no finite coverage rather than an artificial large value.
{% enddocs %}

{% docs available_to_promise %}
Available to promise (ATP) is physical on-hand inventory less units already allocated. It represents stock that can still be committed without relying on future receipts.
{% enddocs %}

{% docs echelon %}
An echelon is a level in Meridian's replenishment network: national DC, regional DC, branch, then customer onsite. Each location retains its parent path so inventory and service can be analyzed at any network level.
{% enddocs %}
