# Financial Data Package

This document defines abstract, non-private fields used to enrich local analyst memo context. It must not contain account snapshots, API keys, generated answers, or time-sensitive output values.

## Financial Conditions Fields

Each item should be structured with:

- key
- name
- value
- unit
- observation_date
- source
- source_tier
- freshness
- status
- error
- interpretation_hint
- risk_relevance

## Configured FRED Fields

The following fields are configured through `configs/data_sources.yaml` and fetched through the local FRED provider:

| Key | FRED series | Unit | Purpose |
| --- | --- | --- | --- |
| high_yield_spread | BAMLH0A0HYM2 | percent | Credit-stress context for distinguishing normal pullbacks from credit pressure. |
| vix | VIXCLS | index | Volatility-stress context, not a standalone trading signal. |
| real_yield_10y | DFII10 | percent | Discount-rate and gold opportunity-cost context. |
| breakeven_inflation_10y | T10YIE | percent | Market-implied inflation-expectation context. |
| yield_curve_10y2y | T10Y2Y | percentage_points | Yield-curve and recession-pressure context, not a standalone recession call. |

## Explicitly Unavailable Fields

The following fields are included as structured limitations when no stable configured source is available:

| Key | Status | Boundary |
| --- | --- | --- |
| valuation_proxy | not_available | Do not infer PE, forward PE, CAPE, earnings yield, or valuation percentiles. |
| fedwatch_probability | not_available | Do not infer FedWatch or market-implied rate-probability values. |

## Interpretation Boundaries

- Credit spread helps distinguish normal pullback from credit stress, but is not a standalone crisis signal.
- VIX indicates volatility stress, not long-term return forecast.
- Real yield affects growth equity and gold through discount-rate and opportunity-cost channels.
- Missing valuation data must not be inferred by the model.
- Missing FedWatch probability must not be inferred by the model.
