# pipeline/

Legacy v1 per-module runners. One CLI per model + a master `run_all.py`. Kept for debugging and single-module re-runs without spinning up the DAG.

**For production, use [orchestrator/scheduler.py](../orchestrator/scheduler.py) instead.** The DAG runner writes `run_audit`, handles tenancy, skips on upstream failure, and supports events — this folder does none of that.

## Files

| File | Purpose |
|------|---------|
| `run_all.py` | Master linear runner (v1). Equivalent to `python main.py`. No DAG, no audit. |
| `run_feature_table.py` | Rebuilds all 6 feature tables. Must run first if downstream modules need fresh features. |
| `run_s1_ar_prediction.py` | Full S1 pipeline: input_format → preprocessing → model_training → evaluate. |
| `run_s2_ap_prediction.py` | Full S2 pipeline (same 4 stages). |
| `run_credit_risk.py` | Full credit-risk classification pipeline. |
| `run_s3_wip_forecast.py` | S3 rule-based forecast: input → forecast_engine → output. |
| `run_s4_pipeline_forecast.py` | S4 rule-based. |
| `run_s5_contingent_inflows.py` | S5 rule-based. |
| `run_s6_expense_forecast.py` | S6 rule-based. |
| `run_s7_cash_aggregation.py` | S7 aggregation (normalise → trust → dedup → audit). Requires S1–S6 outputs. |
| `run_recommendation_engine.py` | Reads S7 + credit_risk, produces ranked recommendations. |
| `__init__.py` | Empty package marker. |

## Run individually

Each file is directly executable:

```bash
python pipeline/run_feature_table.py
python pipeline/run_s1_ar_prediction.py
python pipeline/run_s7_cash_aggregation.py
```

Or run everything linearly:

```bash
python pipeline/run_all.py
```

## Role in orchestration pipeline

**None in production.** The DAG runner ([orchestrator/scheduler.py](../orchestrator/scheduler.py)) calls `steps/*` directly, bypassing these runners.

These files are useful for:
- Debugging a single module without the DAG overhead.
- Re-running a stage without triggering downstream tasks.
- Preserving v1 behaviour for regression testing during the v2 migration.

## Migration note

If a v1 runner ever diverges from what the DAG does, the DAG is the source of truth. Update this folder to match — or delete it once every consumer has moved to the DAG entry point.

## Related

- Task logic: [steps/](../steps/).
- Production equivalent: [orchestrator/scheduler.py](../orchestrator/scheduler.py).
