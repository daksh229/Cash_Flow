# steps/s1_ar_prediction/

**S1 — AR Collections Prediction.** For each open AR invoice, predicts the expected `days_to_pay`. Hybrid LightGBM (primary) + Random Forest (baseline), with thin-data split analysis.

## Files

| File | Stage | Purpose |
|------|-------|---------|
| `input_format.py` | 1 | Loads `invoice_features`, `customer_features`, `collections_features`, `customer_payment_scores` from the feature store. Merges on `customer_id` / `invoice_id`. |
| `preprocessing.py` | 2 | Derives target `days_to_pay` from payments table, filters outliers (0–365 days), encodes categoricals (amount bucket, risk segment, escalation), time-based 80/20 split. |
| `model_training.py` | 3 | Trains LightGBM + Random Forest. Logs CV MAE, feature importance, saves pickles. Runs shared thin-data split metrics (wired in v2.1 via `steps/shared/thin_data.py`). Tracks the run in MLflow. |
| `evaluate.py` | 4 | MAE/RMSE/R²/MAPE/MedianAE on train + test. Error-bucket distribution (within 3/7/14/30 days). Saves `payment_predictions.csv` + `s1_ar_forecast.csv` and a metrics report. |
| `__init__.py` | — | Package marker. |

## Config that drives it

[config/s1_ar_prediction.yml](../../config/s1_ar_prediction.yml):
- `features.*` — which feature columns to use.
- `primary_model.hyperparameters` + `baseline_model.hyperparameters`.
- `split` — `time_based` vs `random`.
- `evaluation.thin_data_threshold` — default 10 invoices.
- `cold_start.tau` + `cold_start.min_customer_n` (v2.1).
- `model_selector.degradation_threshold_pct` (v2.1).

## Run individually

```bash
python pipeline/run_s1_ar_prediction.py
```

Or the 4 stages manually:

```python
import yaml
from steps.s1_ar_prediction import input_format, preprocessing, model_training, evaluate

with open("config/s1_ar_prediction.yml") as f:
    cfg = yaml.safe_load(f)
with open("config.yml") as f:
    master_cfg = yaml.safe_load(f)

merged    = input_format.run(cfg)
prepped   = preprocessing.run(merged, cfg)
training  = model_training.run(prepped, cfg, master_cfg)
metrics   = evaluate.run(training, cfg, master_cfg)
```

## Role in orchestration pipeline

Invoked by the DAG after `feature_table` succeeds. Output lands in `forecast_outputs` and feeds S7 aggregation.

Triggered on:
- Full pipeline run (`python -m orchestrator.scheduler`).
- Event-driven partial re-run: `invoice.created` / `invoice.paid` / `invoice.updated` → `Scheduler.run_subgraph(["s1_ar_prediction"])`.
- Volume trigger: 100 new invoice events (config default) → full S1 retrain.

## Outputs

| Path | Content |
|------|---------|
| `models/s1_ar_prediction/lgbm_model.pkl` | Primary model |
| `models/s1_ar_prediction/rf_model.pkl` | Baseline model |
| `Data/forecast_outputs/s1_payment_predictions.csv` | Per-invoice predictions |
| `Data/forecast_outputs/s1_ar_forecast.csv` | Unified forecast format |
| `reports/s1_ar_prediction/evaluation_metrics.csv` | Metric snapshots |
| `mlruns/...` | MLflow artefacts |

## Related

- Shared helpers: [steps/shared/cold_start.py](../shared/), [steps/shared/model_selector.py](../shared/), [steps/shared/thin_data.py](../shared/).
- Consumer: [steps/s7_cash_aggregation/](../s7_cash_aggregation/) and the recommendation engine.
