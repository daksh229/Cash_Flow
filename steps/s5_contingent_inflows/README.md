# steps/s5_contingent_inflows/

**S5 — Contingent Inflows Forecast.** Deterministic. Schedules known non-recurring inflows: loans, grants, tax refunds, insurance claims, other. No ML — pure rule application.

## Files

| File | Stage | Purpose |
|------|-------|---------|
| `input_format.py` | 1 | Loads `contingent_inflows.csv` (seeded from Data Hub or manual entry). Applies horizon filter. |
| `forecast_engine.py` | 2 | Applies `receipt_lag_days` per approval status; assigns confidence tier (APPROVED → HIGH, COMMITTED → HIGH, PENDING → MEDIUM, CONTINGENT → LOW). |
| `output.py` | 3 | Saves `s5_contingent_detail.csv` + `s5_contingent_forecast.csv`. |
| `__init__.py` | — | Package marker. |

## Config

[config/s5_contingent_inflows.yml](../../config/s5_contingent_inflows.yml):
- `confidence_by_approval` — approval status → HIGH/MEDIUM/LOW mapping.
- `receipt_lag_days` — per category / approval combo.
- `horizon_days` — forecast window.

## Run individually

```bash
python pipeline/run_s5_contingent_inflows.py
```

## Role in orchestration pipeline

**No dependencies.** Runs in parallel with feature_table and every other module. Output feeds S7.

## Related

- SDD: S5 "Contingent Inflows" section.
- Trust score in S7: S5 has a high default trust (`0.90`) because the source is deterministic.
- Consumer: S7.
