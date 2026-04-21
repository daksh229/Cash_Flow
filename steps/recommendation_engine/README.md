# steps/recommendation_engine/

**Recommendation Engine (RE).** Ranks actionable treasury recommendations across three levers (collections acceleration, vendor deferral, expense deferral). Plus the v2.1 feedback loop that captures user accept/reject and proposes new scoring weights.

## Files

| File | Purpose |
|------|---------|
| `input_format.py` | Loads S7 daily cash position, S1/S2 predictions, overdue invoices, credit-risk scores. |
| `forecast_engine.py` | Generates candidate scenarios per lever, scores each on 4 dimensions (`cash_improvement`, `risk_reduction`, `target_alignment`, `feasibility`), applies constraints (min cash floor, Tier-1 vendor protection), ranks. |
| `output.py` | Writes `recommendations_ranked.csv` + summary. |
| `feedback_store.py` | *(v2.1)* `record(recommendation_id, lever, action, predicted_cash_impact, ...)` + `attach_realised_impact(id, amount)` + `load_training_frame()`. Backed by `recommendation_feedback` table. |
| `weight_tuner.py` | *(v2.1)* Non-negative least-squares fit over accepted recommendations with realised impact. Proposes new `scoring_weights` → writes to `reports/re_weights/<tenant>.json`. Advisory only (operator promotes). |
| `__init__.py` | Package marker. |

## Config

[config/recommendation_engine.yml](../../config/recommendation_engine.yml):
- `scoring_weights.{cash_improvement, risk_reduction, target_alignment, feasibility}` — placeholders per Q11.
- `levers.{collections, vendor_deferral, expense_deferral}.enabled` + per-lever caps.
- `constraints.{min_cash_balance, tier1_vendor_deferral}`.

## Run individually

Ranking (the normal 3-stage pipeline):

```bash
python pipeline/run_recommendation_engine.py
```

Feedback + tuner (v2.1):

```python
from steps.recommendation_engine.feedback_store import record, attach_realised_impact
record(recommendation_id="REC-42", lever="collections",
       action="accepted", predicted_cash_impact=50_000,
       actor="alice",
       payload={"score_components": {
           "cash_improvement": 0.9, "risk_reduction": 0.2,
           "target_alignment": 0.5, "feasibility": 0.8,
       }})
attach_realised_impact("REC-42", realised=45_000)
```

Propose new weights:

```bash
python -m steps.recommendation_engine.weight_tuner --tenant default --min-samples 20
```

## Role in orchestration pipeline

**Last task in the DAG.** Depends on S7 + credit_risk (see [orchestrator/dependencies.py](../../orchestrator/dependencies.py)). Runs once per full pipeline. Emits `forecast.published` when done (via [ingestion/outbound.py](../../ingestion/outbound.py)).

Feedback loop (async, not in the DAG):
1. User accepts a rec via `POST /recommendations/feedback` ([app/routers/recommendations.py](../../app/routers/recommendations.py)).
2. Weeks later, realised cash impact arrives via `attach_realised_impact` or the reconciliation job.
3. Operator runs `weight_tuner` → reviews the proposal → updates the YAML → triggers a new run.

## Related

- Tables: `recommendation_feedback` in [db/models.py](../../db/models.py).
- API: [app/routers/recommendations.py](../../app/routers/recommendations.py).
- SDD: "Recommendation Engine" section.
