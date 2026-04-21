# tests/integration/

Multi-module tests that exercise the persistence + orchestration path together. Still fast — ephemeral sqlite per test — but they cross module boundaries.

## Files

| File | What it verifies |
|------|------------------|
| `test_dag_with_audit.py` | Running a DAG writes a `RunAudit` row with the correct status; failed tasks mark the audit row `failed` and record the error. Exercises [orchestrator/dag.py](../../orchestrator/dag.py) + [db/models.py](../../db/models.py) together. |
| `test_event_to_subgraph.py` | `invoice.created` event → listener calls `Scheduler.run_subgraph(["s1_ar_prediction"])`. Same for `bill.paid` → S2 and `customer.updated` → feature rebuild. `Scheduler.run_subgraph` is monkey-patched so the test doesn't actually retrain. Exercises [events/](../../events/) + [orchestrator/](../../orchestrator/) together. |
| `__init__.py` | Package marker. |

## Run individually

```bash
pytest tests/integration -v

# One file
pytest tests/integration/test_event_to_subgraph.py -v
```

## Role in orchestration pipeline

Run alongside unit tests on every PR. Integration tests catch the class of bugs where each module passes its own unit tests but the **glue** between them is wrong — e.g. the event bus persists but the listener never fires, or the DAG runs tasks but forgets to write audit.

Both tests currently pass in ~1 second thanks to the ephemeral sqlite fixture.

## Related

- Fixtures: [tests/conftest.py](../conftest.py) (`tmp_db`, `reset_event_bus`).
- Smoke tests (heavier, manual): [smoke_test_v2_1.py](../../smoke_test_v2_1.py) covers the v2.1 modules end-to-end.
