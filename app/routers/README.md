# app/routers/

Modular FastAPI routers for v2.1 features. Each router is included in the main app via `app.include_router(...)`.

## Files

| File | Mount path | Endpoints |
|------|-----------|-----------|
| `non_po_expenses.py` | `/expenses/non-po` | `POST /`, `GET /`, `DELETE /{id}`. Captures non-PO operational expenses. Emits `bill.created` on submit so S6 sees them. |
| `recommendations.py` | `/recommendations` | `POST /feedback`, `POST /{id}/realised`. Captures user accept/reject + realised cash impact for the weight-tuner feedback loop. |
| `__init__.py` | — | Empty marker. |

Both routers require bearer-token auth + `X-Tenant-Id` header. Roles enforced via [security/rbac.py](../../security/rbac.py):
- `VIEWER` can `GET`.
- `ANALYST` can `POST` / `DELETE`.
- `ADMIN` can do everything.

## Run individually

Routers don't run standalone — they must be mounted on a FastAPI app. Quick test with a minimal app:

```python
from fastapi import FastAPI
from app.routers.non_po_expenses import router as non_po_router

app = FastAPI()
app.include_router(non_po_router)
# uvicorn this module to test in isolation
```

Or the easier route — use the main app and hit the endpoints directly:

```bash
python app/api.py
# then
curl -X POST http://localhost:8000/expenses/non-po \
     -H "Authorization: Bearer <token>" \
     -H "X-Tenant-Id: default" \
     -H "Content-Type: application/json" \
     -d '{"category": "Legal", "amount": 150000, "expected_date": "2026-05-15T00:00:00"}'
```

## Role in orchestration pipeline

These routers are **ingress points** that produce events, not part of the pipeline itself. The chain:

1. User submits → router writes to DB → emits event.
2. Event bus dispatches → listener calls `Scheduler.run_subgraph(...)`.
3. Downstream model re-trains / re-scores.

## Related

- Tokens: [security/auth.py](../../security/auth.py) (`issue_token(...)`).
- Tenant context: `X-Tenant-Id` header → [security/tenant_context.py](../../security/tenant_context.py).
- Tables: `non_po_expenses`, `recommendation_feedback` in [db/models.py](../../db/models.py).
