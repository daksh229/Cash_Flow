# reconciliation/

Closes the loop: joins what we forecasted against what actually happened in the ERP. Produces the composite cash-accuracy KPI input.

## Files

| File | Purpose |
|------|---------|
| `reconcile.py` | `record_actual(reference_id, source_type, actual_date, actual_amount, ...)` inserts an `ActualOutcome` row. `reconcile(run_id?, tenant_id?)` joins `forecast_outputs` ⋈ `actual_outcomes` on `(tenant_id, reference_id)`, computes `match_rate`, `mae_days`, `bias_days`, `mape_amount`, and writes a CSV + summary JSON under `reports/reconciliation/<tenant>_<run>.*`. CLI via `__main__`. |
| `__init__.py` | Re-exports `reconcile`, `record_actual`. |

## Run individually

Record an actual (typically triggered by Data Hub push, but can be manual):

```python
from reconciliation import record_actual
record_actual(
    reference_id="INV-123",
    source_type="AR",
    actual_date="2026-05-02",
    actual_amount=125_000,
)
```

Run reconciliation for the latest full run:

```bash
python -m reconciliation.reconcile --tenant default --run-id <run_id>
```

Output:
- `reports/reconciliation/<tenant>_<run>.csv` — one row per forecast (matched or not).
- `reports/reconciliation/<tenant>_<run>.summary.json` — aggregate metrics.

## Role in orchestration pipeline

Runs **after** a production pipeline run (not part of the DAG itself). Typical cadence:

1. Daily DAG produces forecasts → `forecast_outputs` rows (with `reference_id`).
2. Data Hub pushes realised cash events → `record_actual(...)` inserts into `actual_outcomes`.
3. Operator (or scheduled job) runs `python -m reconciliation.reconcile`.
4. [monitoring/cash_accuracy.py](../monitoring/cash_accuracy.py) reads the summary JSON → composite KPI → Prometheus gauge.
5. (Optional) [steps/recommendation_engine/weight_tuner.py](../steps/recommendation_engine/weight_tuner.py) reads the matched-impact rows to propose new weights.

## Related

- Tables: `actual_outcomes` + `forecast_outputs` in [db/models.py](../db/models.py).
- KPI consumer: [monitoring/cash_accuracy.py](../monitoring/cash_accuracy.py).
- Feedback consumer: [steps/recommendation_engine/feedback_store.py](../steps/recommendation_engine/feedback_store.py) (`attach_realised_impact`).
