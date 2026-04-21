# app/

Web-facing layer. FastAPI backend + Streamlit frontend + modular routers + standalone Streamlit pages.

## Files

| File / folder | Purpose |
|---------------|---------|
| `api.py` | Main FastAPI application. Loads models, mounts routers, exposes prediction + forecast + recommendation + lookup + health endpoints. Runs on port 8000. |
| `frontend.py` | Main Streamlit dashboard. Covers all 9 modules + overall cash position. Runs on port 8501. |
| `routers/` | Modular FastAPI routers for v2.1 endpoints (non-PO expenses, RE feedback). See [routers/README.md](routers/README.md). |
| `pages/` | Standalone Streamlit pages for focused tasks (non-PO capture form). See [pages/README.md](pages/README.md). |

## Run individually

```bash
# Backend
python app/api.py                  # http://localhost:8000
#                                   docs at /docs
#                                   health at /health/live, /health/ready
#                                   metrics at /metrics

# Frontend (in a separate terminal)
streamlit run app/frontend.py      # http://localhost:8501

# Extra page
streamlit run app/pages/non_po_expense_form.py
```

## Role in orchestration pipeline

Not part of the DAG. The API and frontend are consumers of what the DAG produces:

- `api.py` reads `forecast_outputs` + `reports/*` + model pickles at request time.
- `frontend.py` calls the API for all data.
- The v2.1 routers (`routers/`) also **produce** work — submitting a non-PO expense emits `bill.created`, which the event bus dispatches back to the DAG.

## Wiring v2.1 additions in api.py

If you don't already have them in `api.py`, add:

```python
from app.routers.non_po_expenses import router as non_po_router
from app.routers.recommendations import router as rec_router
from ingestion import data_hub_router, register_outbound_publisher
from events.listeners import register_default_listeners
from orchestrator.volume_trigger import register_volume_listeners
from monitoring.health import register_health_routes

app.include_router(non_po_router)
app.include_router(rec_router)
app.include_router(data_hub_router)
register_health_routes(app)
register_default_listeners()
register_volume_listeners()
register_outbound_publisher()
```

## Related

- API reference: [README_v2.md §24](../README_v2.md#24-api-reference).
- Auth required on write endpoints: [security/auth.py](../security/auth.py) + [security/rbac.py](../security/rbac.py).
