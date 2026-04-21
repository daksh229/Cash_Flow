# steps/s7_cash_aggregation/

**S7 — Cash Event Aggregation.** The unification layer. Ingests S1–S6 outputs, normalises to a canonical event schema, assigns trust scores, deduplicates overlapping events, and writes a per-run audit + lineage record.

## Files

| File | Purpose |
|------|---------|
| `input_format.py` | Reads all S1–S6 CSV outputs from `Data/forecast_outputs/`. |
| `normalization.py` | Canonical event schema: `event_id, source_model, entity_id, event_date, amount, direction, confidence, currency, raw`. Per-source field map handles each upstream module's quirks. |
| `trust_scoring.py` | `trust_score = source_trust × confidence`. `source_trust` blends a static baseline per module with a bump from recent MAE/F1 metrics (read from `reports/<model>*metrics*.json`). |
| `dedup_engine.py` | Buckets events by `(entity_id, rounded_amount, date_window_days)`. Within a bucket, highest `trust_score` wins. Losers are recorded in `duplicates_of` for audit. |
| `audit_model.py` | Per-run summary to `reports/s7_audit.jsonl` + lineage edge via [audit/lineage_tracker.py](../../audit/). Records input/kept/dropped counts per source. |
| `forecast_engine.py` | Orchestrates the above: normalise → trust → dedup → audit. |
| `output.py` | Writes daily/weekly/monthly roll-ups to `Data/forecast_outputs/s7_*.csv`. |
| `__init__.py` | Package marker. |

## Config

[config/s7_cash_aggregation.yml](../../config/s7_cash_aggregation.yml):
- `source_trust` — per-module baseline (S5/S6 high because deterministic; S4 lowest because CRM is noisy).
- `dedup.date_window_days` — how many days count as "same event". Default 5.
- `dedup.amount_round` — rounding (power of 10) when bucketing.
- `opening_balance` — starting cash for the aggregated ledger.

## Run individually

```bash
python pipeline/run_s7_cash_aggregation.py
```

Requires S1–S6 outputs to already exist in `Data/forecast_outputs/`.

## Role in orchestration pipeline

**Synchronisation point.** Depends on S1, S2, S3, S4, S5, S6 per [orchestrator/dependencies.py](../../orchestrator/dependencies.py). If any of them fails, S7 is marked `skipped`.

Output is the single source of truth for downstream consumers:
- `forecast_outputs` DB table (v2.1 target, in progress).
- `Data/forecast_outputs/s7_daily_position.csv` (current).
- Consumed by the recommendation engine and the API.

## Related

- Lineage: [audit/lineage_tracker.py](../../audit/).
- Trust baselines: [tests/regression/baselines.yml](../../tests/regression/baselines.yml) ships `s7_cash_aggregation.dedup_rate`.
- SDD: S7 "Cash Event Normalisation & Aggregation" section.
