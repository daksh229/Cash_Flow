# steps/s3_wip_forecast/

**S3 — WIP / Project-Milestone Billing Forecast.** Rule-based. For each in-progress project milestone, forecasts when it will be billed and collected.

## Files

| File | Stage | Purpose |
|------|-------|---------|
| `input_format.py` | 1 | Loads milestones + customer payment delays (from `customer_features`). |
| `forecast_engine.py` | 2 | 5-step rule pipeline: completion probability → invoice date → payment-delay lookup → cash date → confidence tier. |
| `output.py` | 3 | Saves `s3_wip_detail.csv` + standardised `s3_wip_forecast.csv`. |
| `__init__.py` | — | Package marker. |

## Config

[config/s3_wip_forecast.yml](../../config/s3_wip_forecast.yml):
- `completion_threshold` — minimum `%complete` to consider a milestone billable.
- `invoice_lag_days` — time from completion to invoice issue.
- `confidence_mapping` — % complete → HIGH / MEDIUM / LOW.

## Run individually

```bash
python pipeline/run_s3_wip_forecast.py
```

## Role in orchestration pipeline

Runs after `feature_table` in parallel with ML modules. Output feeds S7 aggregation.

Not yet wired to an event trigger — a project-milestone update in Data Hub should emit a `project.updated` event and trigger a targeted re-run. This is a small extension: add the event name in [events/triggers.py](../../events/triggers.py) + a listener in [events/listeners.py](../../events/listeners.py).

## Related

- SDD: S3 "WIP Billing Forecast" section.
- Consumer: S7.
