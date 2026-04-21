# steps/shared/

Cross-module helpers reused by S1, S2, Credit Risk (and available to rule-based modules). All four live here because they address the same class of problem: "what to do when the per-customer signal isn't strong enough."

## Files

| File | Purpose |
|------|---------|
| `cold_start.py` | `GlobalPrior` — 3-level hierarchical prior (customer / segment / global) with empirical-Bayes shrinkage. Segment key = `(risk_segment, amount_bucket, season)`. `fit(df)` + `predict(df)` + `save()` + `load()`. Addresses the "core architectural unlock" (Q8). |
| `model_selector.py` | `select(model_key, entity_stats, config) -> 'primary' | 'baseline' | 'prior'` using recent metric history + per-entity sample size + model registry state. `load_artifact(model_key, choice)`. `predict(...)` for one-shot serve. |
| `model_registry.py` | Promotion state machine for `(tenant, model_key, variant)`. `promote / demote / set_shadow / active_variants / history`. Backed by `model_registry` table. |
| `thin_data.py` | `split_metrics(X_test, y_true, y_pred, threshold, count_col)` — per-bucket MAE so we can tell whether the model is carrying the thin-data or rich-data segment. `log_to_mlflow(...)` helper. |
| `__init__.py` | Empty — access modules by name. |

## Run individually

None have a CLI. Usage examples:

```python
# Prior fit during training
from steps.shared.cold_start import GlobalPrior
prior = GlobalPrior.fit(history_df, target_col="days_to_pay")
prior.save()

# Selector at serve time
from steps.shared.model_selector import predict
result = predict("s1_ar_prediction", feature_row, entity_stats, cfg)
# -> {"prediction": 27.3, "used": "primary"}

# Registry after training
from steps.shared.model_registry import promote
promote("s1_ar_prediction", "primary", version="abc123",
        metric_name="test_mae", metric_value=6.4)

# Thin-data metrics in an evaluate step
from steps.shared.thin_data import split_metrics, log_to_mlflow
m = split_metrics(X_test, y_test, lgb_pred, threshold=10, count_col="invoice_count")
log_to_mlflow(m, mlflow_mod=mlflow)
```

## Role in orchestration pipeline

Invoked from inside `steps/s1_ar_prediction/`, `steps/s2_ap_prediction/`, `steps/credit_risk/` — not directly by the DAG. Call sites today:

- `steps/s1_ar_prediction/model_training.py` → `split_metrics` + `log_to_mlflow` (wired v2.1).
- `steps/s2_ap_prediction/model_training.py` → same.
- Serving code should always go through `model_selector.predict(...)` rather than loading pickles directly.

## Related

- Tables: `model_registry` in [db/models.py](../../db/models.py).
- Config blocks: `cold_start`, `model_selector`, `evaluation.thin_data_threshold` in the per-model YAMLs.
