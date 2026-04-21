# monitoring/

Observability layer: Prometheus metrics, health probes, structured logging, composite cash-accuracy KPI.

## Files

| File | Purpose |
|------|---------|
| `metrics.py` | `MetricsRegistry` + `metrics` singleton. Exposes `cashflow_runs_total{pipeline,status}`, `cashflow_run_duration_seconds`, `cashflow_model_mae{model}`, `cashflow_events_emitted_total`, `cashflow_db_errors_total`. Falls back to an in-memory dict when `prometheus_client` isn't installed. |
| `health.py` | `HealthCheck.live()` / `HealthCheck.ready()` and `register_health_routes(app)` to mount `/health/live`, `/health/ready`, `/metrics` on a FastAPI app. |
| `logging_config.py` | `setup_logging(level, fmt)` + `with_run_id(logger, run_id)`. Switches between human-readable and JSON format via `CASHFLOW_LOG_FORMAT` env var. |
| `cash_accuracy.py` | Client KPI computation. Reads the latest reconciliation summary and produces `cash_accuracy` + `days_accuracy` + composite `kpi = cash_weight·cash + days_weight·days`. Exposed via Prometheus gauge. |
| `__init__.py` | Re-exports `MetricsRegistry`, `metrics`, `HealthCheck`, `register_health_routes`, `setup_logging`. |

## Run individually

```bash
# Compute KPI for a tenant after a reconciliation run
python -m monitoring.cash_accuracy --tenant default --run-id smoke-run
```

Or in code:

```python
from monitoring import metrics, setup_logging
setup_logging(level="INFO", fmt="json")
with metrics.time_run("manual_test"):
    ...   # Prometheus counter + histogram updated
```

## Role in orchestration pipeline

- `metrics.time_run(pipeline)` wraps DAG runs in [orchestrator/scheduler.py](../orchestrator/scheduler.py) (or wherever a pipeline runs).
- `register_health_routes(app)` is called once at FastAPI startup in [app/api.py](../app/api.py).
- `cash_accuracy.compute(tenant_id)` runs after [reconciliation/reconcile.py](../reconciliation/reconcile.py) writes its summary JSON.

## Related

- Input for `cash_accuracy`: `reports/reconciliation/<tenant>_<run>.summary.json`.
- KPI weights configured in `config.yml → kpi:`.
- Regression gate: [tests/regression/baselines.yml](../tests/regression/baselines.yml) under `cash_kpi:`.
