# audit/

Append-only audit trail + dataset lineage graph. Answers "what ran, when, by whom, and where did this dataset come from?"

## Files

| File | Purpose |
|------|---------|
| `audit_logger.py` | JSONL audit trail writer. Thread-safe. Default path `reports/audit.jsonl`. Public API: `audit.record(action, actor, run_id, **fields)` and `audit.tail(n)`. |
| `lineage_tracker.py` | Dataset lineage edges with `git_rev` + `config_hash`. Default path `reports/lineage.jsonl`. Public API: `lineage.record(output, inputs, producer, run_id, config)` and `lineage.trace(output, depth)`. |
| `__init__.py` | Re-exports the two singletons: `audit`, `lineage`. |

## Run individually

Neither file has a CLI — they're imported. Quick demo:

```python
from audit import audit, lineage
audit.record("manual_test", actor="me", run_id="r1", note="hello")
lineage.record(output="cash_forecast", inputs=["s1", "s2"], producer="s7", run_id="r1")
print(lineage.trace("cash_forecast"))
```

## Role in orchestration pipeline

- `orchestrator/dag.py` writes one `RunAudit` DB row per run (not a call here — separate).
- `steps/s7_cash_aggregation/audit_model.py` calls `lineage.record(...)` after every aggregation run.
- Future: every `evaluate.py` should call `audit.record("eval_complete", ...)`.

## Related

- Upstream: called by [steps/s7_cash_aggregation/audit_model.py](../steps/s7_cash_aggregation/audit_model.py), [reconciliation/reconcile.py](../reconciliation/reconcile.py).
- Downstream: files end up in `reports/audit.jsonl` and `reports/lineage.jsonl` (ingested by SIEM/BI tooling).
