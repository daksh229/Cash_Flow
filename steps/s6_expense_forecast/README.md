# steps/s6_expense_forecast/

**S6 — Expense Forecast.** Category-based scheduling. Forecasts outflows from salary, tax, rent, PO-based, renewals, one-time, seasonal — plus the new **non-PO expense** capture path (v2.1).

## Files

| File | Stage | Purpose |
|------|-------|---------|
| `input_format.py` | 1 | Loads `expense_schedule.csv`. Should be extended to also read from the `non_po_expenses` table where `is_active = true`. |
| `forecast_engine.py` | 2 | Applies `payment_lag_days` by category. Assigns confidence (HIGH for FIXED like salary/rent, MEDIUM for PERIODIC, LOW for VARIABLE). Outputs as negative amounts (outflows). |
| `output.py` | 3 | Saves `s6_expense_detail.csv` + `s6_expense_forecast.csv`. |
| `__init__.py` | — | Package marker. |

## Config

[config/s6_expense_forecast.yml](../../config/s6_expense_forecast.yml):
- `confidence_by_category` — category → tier mapping.
- `payment_lag_days` — days from commitment to cash-out.
- `horizon_days`.

## Run individually

```bash
python pipeline/run_s6_expense_forecast.py
```

## Role in orchestration pipeline

No dependencies — runs in parallel. Output feeds S7.

**v2.1 extension:** when a user submits a non-PO expense via `POST /expenses/non-po`, the router emits a `bill.created` event. Until S6 is wired to listen to that event (or to read from `non_po_expenses` at ingest time), the new expense only shows up in the **next** full batch run. Small follow-up: extend `input_format.py` to `UNION ALL` the DB table.

## Related

- Non-PO capture: [app/routers/non_po_expenses.py](../../app/routers/non_po_expenses.py), [app/pages/non_po_expense_form.py](../../app/pages/non_po_expense_form.py).
- Table: `non_po_expenses` in [db/models.py](../../db/models.py).
- SDD: S6 "Expense Forecast" section.
