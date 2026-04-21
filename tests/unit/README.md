# tests/unit/

Fast, module-scoped tests. Each file maps 1:1 to a v2/v2.1 infrastructure component. No external services.

## Files

| File | What it verifies |
|------|------------------|
| `test_dag.py` | Topological order, upstream-failure skip propagation, cycle detection, unknown-dependency guard. Covers [orchestrator/dag.py](../../orchestrator/dag.py). |
| `test_event_bus.py` | Subscribe/emit, DB persistence of events, `processed=1` marking on success, `processed=0` on handler failure, event-name catalogue enumeration. Covers [events/event_bus.py](../../events/event_bus.py) + [events/triggers.py](../../events/triggers.py). |
| `test_feature_registry.py` | Unknown feature-set rejection, write/read round-trip, entity filter, deterministic version strings. Covers [feature_store/registry.py](../../feature_store/registry.py) + [versioning.py](../../feature_store/versioning.py). |
| `test_retry_and_breaker.py` | `@retry` succeeds after transient failure, doesn't swallow non-retryable, circuit breaker opens after threshold + closes after successful half-open probe. Covers [core/retry.py](../../core/retry.py) + [core/circuit_breaker.py](../../core/circuit_breaker.py). |
| `test_audit_and_lineage.py` | Audit JSONL round-trip, lineage trace walks backwards. Covers [audit/audit_logger.py](../../audit/audit_logger.py) + [audit/lineage_tracker.py](../../audit/lineage_tracker.py). |
| `__init__.py` | Package marker. |

## Run individually

```bash
pytest tests/unit -v

# One file
pytest tests/unit/test_dag.py -v

# One test
pytest tests/unit/test_dag.py::test_cycle_detection -v
```

Every test uses the `tmp_db` fixture (ephemeral sqlite, auto-migrated). No side effects on `Data/cashflow.db`.

## Role in orchestration pipeline

Run on every PR and pre-deploy. A unit-test failure should block merge. These should pass in under 10 seconds total (current run: ~5 seconds for 18 tests).

## Related

- Fixtures: [tests/conftest.py](../conftest.py).
- Components under test: [orchestrator/](../../orchestrator/), [events/](../../events/), [feature_store/](../../feature_store/), [core/](../../core/), [audit/](../../audit/).
