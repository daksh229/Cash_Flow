# steps/

All forecasting/prediction logic. The DAG invokes files here; no networking, no DB-schema management, no event dispatching happens inside this folder.

## Layout

| Path | Type | Purpose |
|------|------|---------|
| `feature_table.py` | shared | Builds all 6 feature tables from raw data. Runs first in the DAG. |
| `s1_ar_prediction/` | ML 4-stage | AR collections — predict `days_to_pay` per invoice. |
| `s2_ap_prediction/` | ML 4-stage + treasury | AP payments — predict timing + apply liquidity gate + treasury rules. |
| `credit_risk/` | ML classification | Classify customers LOW / MEDIUM / HIGH. |
| `s3_wip_forecast/` | Rule-based 3-stage | Project-milestone billing forecast. |
| `s4_pipeline_forecast/` | Rule-based 3-stage | Sales pipeline cohort forecast. |
| `s5_contingent_inflows/` | Rule-based 3-stage | Loans, grants, refunds, insurance. |
| `s6_expense_forecast/` | Rule-based 3-stage | Salary, tax, PO-based, renewals, one-time, seasonal, + non-PO expenses. |
| `s7_cash_aggregation/` | Aggregation | Normalise → trust-score → dedup → audit. The unified cash position. |
| `recommendation_engine/` | Rule + scoring | Ranked recommendations + feedback capture + weight tuner. |
| `shared/` | Cross-cutting | Cold-start prior, model selector, model registry, thin-data analyser. |

## Two module shapes

**ML modules (S1, S2, Credit Risk)** — 4-stage pipeline:
```
input_format.py  →  preprocessing.py  →  model_training.py  →  evaluate.py
```

**Rule-based modules (S3–S6)** — 3-stage pipeline:
```
input_format.py  →  forecast_engine.py  →  output.py
```

**Special shapes:**
- S2 adds `liquidity_gate.py` + `treasury_logic.py` on top of the 4-stage ML base.
- S7 uses the 3-stage shell but with module files `normalization.py`, `trust_scoring.py`, `dedup_engine.py`, `audit_model.py` called from its `forecast_engine.py`.
- `recommendation_engine/` adds `feedback_store.py` + `weight_tuner.py` outside the 3-stage shell.

## Run individually

All modules follow the DAG entry points — see [pipeline/](../pipeline/) for one-shot CLI runners or invoke through Python:

```python
from steps.s1_ar_prediction import input_format, preprocessing, model_training, evaluate
# 4-stage call chain, each stage's run() consumes the previous stage's return
```

Or via the DAG for any subset:

```python
from orchestrator.scheduler import Scheduler
Scheduler.run_subgraph(["s1_ar_prediction"])
```

## Role in orchestration pipeline

Every task in [orchestrator/dependencies.py](../orchestrator/dependencies.py) maps to one module here. The DAG calls the module's stages in order (via `pipeline/run_*.py` or directly via `scheduler._model_runner`).

Dependencies (from `MODEL_DEPENDENCIES`):
```
feature_table ─► s1, s2, credit_risk, s3, s4
s5, s6                  (no dependencies)
s1..s6        ─► s7
s7, credit_risk ─► recommendation_engine
```

## Shared primitives

Every ML module is encouraged to use [steps/shared/](shared/):
- `cold_start.GlobalPrior` for thin / new entities.
- `model_selector.select` + `load_artifact` at serve time.
- `model_registry.promote/demote` around training.
- `thin_data.split_metrics` in `model_training.py` for per-bucket MAE logging.

## Related

- Orchestrator: [orchestrator/scheduler.py](../orchestrator/scheduler.py).
- Feature reads: [feature_store/](../feature_store/).
- Outputs: `forecast_outputs` table + `Data/forecast_outputs/*.csv` (legacy).
