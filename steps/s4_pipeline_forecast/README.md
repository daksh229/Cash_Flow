# steps/s4_pipeline_forecast/

**S4 — Sales Pipeline Cash Forecast.** Rule-based. Converts CRM pipeline deals (in various sales stages) into expected cash inflows using stage probability × cohort-based payment delay.

## Files

| File | Stage | Purpose |
|------|-------|---------|
| `input_format.py` | 1 | Loads CRM deals + customer payment delays + cohort statistics. |
| `forecast_engine.py` | 2 | `weighted_amount = deal_amount × stage_probability`. Matches each deal to a customer cohort for expected payment delay. Derives `expected_cash_date`. |
| `output.py` | 3 | Saves `s4_pipeline_detail.csv` + standardised `s4_pipeline_forecast.csv`. |
| `__init__.py` | — | Package marker. |

## Config

[config/s4_pipeline_forecast.yml](../../config/s4_pipeline_forecast.yml):
- `stage_probabilities` — `LEAD=0.1, QUALIFIED=0.3, PROPOSAL=0.5, NEGOTIATION=0.7, CLOSED_WON=1.0`.
- `cohort_matching` — grouping logic for delay lookup.
- `invoice_lag_days` — time from close-won to invoice issue.

## Run individually

```bash
python pipeline/run_s4_pipeline_forecast.py
```

## Role in orchestration pipeline

Parallel with S1–S3 after `feature_table`. Output feeds S7.

Event hook to add in future: `deal.updated` → `Scheduler.run_subgraph(["s4_pipeline_forecast"])`.

## Related

- SDD: S4 "Sales Pipeline Forecast" section.
- Consumer: S7.
