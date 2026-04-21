# core/

Cross-cutting primitives: exception hierarchy, retry decorator, circuit breaker. Imported by every other layer.

## Files

| File | Purpose |
|------|---------|
| `exceptions.py` | Domain exceptions: `CashFlowError` (base), `ConfigError`, `DataValidationError`, `UpstreamDataMissing`, `ModelTrainingError`, `ExternalServiceError`. |
| `retry.py` | `@retry(attempts, base_delay, max_delay, retry_on, jitter)` — exponential backoff. Retries `ExternalServiceError` + anything in `retry_on`. |
| `circuit_breaker.py` | `CircuitBreaker(name, failure_threshold, reset_after)` with states `closed` / `open` / `half_open`. Use as decorator or via `.call(fn, ...)`. |
| `__init__.py` | Re-exports all public symbols. |

## Run individually

No CLI. Usage examples:

```python
from core import retry, ExternalServiceError

@retry(attempts=3, base_delay=0.5)
def call_data_hub():
    ...

from core import CircuitBreaker
cb = CircuitBreaker("mlflow", failure_threshold=5, reset_after=30)
result = cb.call(mlflow.log_metric, "mae", 6.2)
```

## Role in orchestration pipeline

Not invoked by the pipeline directly. Other modules decorate their network/DB calls with `@retry` and wrap fragile dependencies with `CircuitBreaker`. The DAG ([orchestrator/dag.py](../orchestrator/dag.py)) inspects `CashFlowError` subclasses to decide whether a task failure should propagate as `skipped` downstream.

## Related

- Used by: [ingestion/](../ingestion/), [monitoring/](../monitoring/), any code that touches external services.
- Unit tests: [tests/unit/test_retry_and_breaker.py](../tests/unit/test_retry_and_breaker.py).
