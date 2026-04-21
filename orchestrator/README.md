# orchestrator/

The dependency-aware DAG runner. Replaces the v1 linear `main.py` with a graph-based executor that skips downstream tasks when upstream fails, records a `run_audit` row per run, and supports partial re-runs.

## Files

| File | Purpose |
|------|---------|
| `dag.py` | `PipelineDAG` class — adds tasks, computes topological order, runs tasks sequentially (parallel-ready), stamps `run_audit` at start + finish, marks downstream as `skipped` when upstream fails. |
| `dependencies.py` | Single source of truth for task edges: `MODEL_DEPENDENCIES = {model_key: [deps]}`. Edit this to change graph shape. |
| `scheduler.py` | High-level entry point. `Scheduler.run_full()` builds the master DAG from `config.yml`. `Scheduler.run_subgraph(keys)` runs a target set + its downstream closure. Also the module `__main__` for `python -m orchestrator.scheduler`. |
| `volume_trigger.py` | Event-counter-based retraining. `register_volume_listeners()` subscribes to ingestion events; when `(tenant, model)` hits its `new_rows_threshold`, fires `Scheduler.run_subgraph([model])` and resets. |
| `__init__.py` | Re-exports `PipelineDAG`, `Task`, `Scheduler`, `MODEL_DEPENDENCIES`. |

## Run individually

```bash
# Full pipeline — the production entry point
python -m orchestrator.scheduler

# Set tenant explicitly
$env:CASHFLOW_TENANT_ID="entity_alpha"; python -m orchestrator.scheduler    # PowerShell
CASHFLOW_TENANT_ID=entity_alpha python -m orchestrator.scheduler            # bash
```

Partial re-runs (Python only):

```python
from orchestrator.scheduler import Scheduler
Scheduler.run_subgraph(["s1_ar_prediction"])   # re-runs feature_table + S1
```

## Role in orchestration pipeline

This folder **is** the orchestration pipeline. Everything in `steps/` is invoked via the DAG:

1. [events/listeners.py](../events/listeners.py) → `Scheduler.run_subgraph(...)` on invoice / bill / customer events.
2. `volume_trigger.py` → `Scheduler.run_subgraph(...)` when event counts cross threshold.
3. `scheduler.py` → builds DAG → calls each task's `run()` in topo order → writes audit rows.

## Related

- Task logic: [steps/](../steps/).
- Events that fire subgraphs: [events/listeners.py](../events/listeners.py).
- Run records: `run_audit` table in [db/models.py](../db/models.py).
- Unit tests: [tests/unit/test_dag.py](../tests/unit/test_dag.py), [tests/integration/test_dag_with_audit.py](../tests/integration/test_dag_with_audit.py).
