# app/pages/

Standalone Streamlit pages — focused single-purpose UIs that can run alongside the main dashboard or embedded into it.

## Files

| File | Purpose |
|------|---------|
| `non_po_expense_form.py` | Form to capture non-PO operational expenses (legal fees, ad-hoc travel, consultancy, ads). Submits to `POST /expenses/non-po` and displays the live list below. |

## Run individually

```bash
# Requires the API to be running (python app/api.py)
streamlit run app/pages/non_po_expense_form.py
```

The page reads three env vars:

| Var | Default | Purpose |
|-----|---------|---------|
| `CASHFLOW_API_URL` | `http://localhost:8000` | Where to POST |
| `CASHFLOW_TOKEN` | (empty) | Bearer token issued via `security.auth.issue_token(...)` |
| `CASHFLOW_TENANT_ID` | `default` | Sent as `X-Tenant-Id` header |

Example setup (PowerShell):

```powershell
$env:CASHFLOW_TOKEN = (python -c "from security import issue_token; print(issue_token('me', roles=['analyst']))")
$env:CASHFLOW_TENANT_ID = "default"
streamlit run app/pages/non_po_expense_form.py
```

## Role in orchestration pipeline

Not part of the DAG. Submissions travel: page → API router → DB + event bus → downstream re-scoring (see [app/routers/non_po_expenses.py](../routers/non_po_expenses.py)).

## Related

- Router: [app/routers/non_po_expenses.py](../routers/non_po_expenses.py).
- Table: `non_po_expenses` in [db/models.py](../../db/models.py).
- Why: SSD + Q&A row 2 — operational expenses skip the PO flow and need a dedicated capture path.
