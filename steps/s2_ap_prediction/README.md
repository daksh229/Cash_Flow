# steps/s2_ap_prediction/

**S2 — AP Payment Prediction + Treasury Logic.** For each vendor bill, predicts payment-timing adjustment, then applies the liquidity gate (cash-floor check) and treasury rules (early-discount, credit-line, cheapest-to-defer).

## Files

| File | Stage | Purpose |
|------|-------|---------|
| `input_format.py` | 1 | Loads `vendor_features`, `bill_features`. Joins on `vendor_id`. |
| `preprocessing.py` | 2 | Derives target `adjustment_delta = actual_payment_days − rule_scheduled_days`. Filters −60..+60 day outliers. Encodes bucket + approval status. Time-based split. |
| `model_training.py` | 3 | Trains LightGBM + RF. Logs thin-data MAE separately (vendors with < `thin_data_threshold` invoices). |
| `evaluate.py` | 4 | Metrics, thin-data split report, error buckets (3/5/10/15 days). Saves `s2_payment_predictions.csv` + `s2_ap_forecast.csv`. |
| `liquidity_gate.py` | post-4 | Decides `pay` / `defer` / `partial` per bill against projected daily balance. Uses `min_cash_floor`, `critical_priorities`, `apply_grace_days`. |
| `treasury_logic.py` | post-4 | Early-payment discount capture + credit-line draw + cheapest-to-defer ranking (`penalty_rate × amount`). |
| `__init__.py` | — | Package marker. |

## Config that drives it

[config/s2_ap_prediction.yml](../../config/s2_ap_prediction.yml):
- `features.*` + model hyperparams.
- `evaluation.thin_data_threshold` — split at `invoice_count < N`.
- `cold_start`, `model_selector` (v2.1).
- **`liquidity_gate.min_cash_floor`** — never breach this balance.
- **`treasury.credit_limit`** — cap for credit-line draw.

## Run individually

```bash
python pipeline/run_s2_ap_prediction.py
```

4 stages + treasury call chain in Python:

```python
from steps.s2_ap_prediction import (
    input_format, preprocessing, model_training, evaluate,
    liquidity_gate, treasury_logic,
)
merged    = input_format.run(cfg)
prepped   = preprocessing.run(merged, cfg)
training  = model_training.run(prepped, cfg, master_cfg)
metrics   = evaluate.run(training, cfg, master_cfg)

# After prediction DataFrame + cash_ledger from S7 are available:
gated   = liquidity_gate.run(predictions, cash_ledger, cfg)
treated = treasury_logic.run(gated, cash_ledger, cfg)
```

## Role in orchestration pipeline

Runs after `feature_table`. Output feeds S7. Event triggers: `bill.*` events → `Scheduler.run_subgraph(["s2_ap_prediction"])`.

Note: the liquidity gate + treasury logic currently run **inside** S2's evaluate/forecast path but need a `cash_ledger` input. In v1 this is approximated; in the production flow the gate should run *after* S7 produces the daily projected balance, then an S2 post-adjustment writes the final payment plan back to `forecast_outputs`.

## Related

- Shared helpers: same as S1.
- Consumers: S7, recommendation engine.
- SDD: S2 "Treasury Logic" section.
