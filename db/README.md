# db/

Persisted data layer. SQLAlchemy engine, schema base, ORM models for every tenant-scoped table.

## Files

| File | Purpose |
|------|---------|
| `connection.py` | Lazy singleton `get_engine()` + context-managed `get_session()`. Reads `database.backend` / `database.url` / `database.path` from `config.yml`; honours `CASHFLOW_DB_URL` env override. SQLite gets `check_same_thread=False`; Postgres gets `pool_size`. |
| `schema.py` | SQLAlchemy `DeclarativeBase` → `Base`. Isolated here to avoid circular imports. |
| `models.py` | Every ORM table. v2 core: `FeatureSnapshot`, `ForecastOutput`, `RunAudit`, `EventLog`. v2.1: `NonPOExpense`, `ActualOutcome`, `FeatureVersion`, `RecommendationFeedback`, `ModelRegistry`, `IngestionDLQ`, `IngestionSeen`. Every row has `tenant_id`. |
| `__init__.py` | Re-exports `get_engine`, `get_session`, `Base`. |
| `migrations/` | One script per schema change (see [migrations/README.md](migrations/README.md)). |

## Run individually

No CLI here. Quick DB poke:

```python
from db.connection import get_session
from db.models import RunAudit

with get_session() as s:
    for r in s.query(RunAudit).order_by(RunAudit.id.desc()).limit(5):
        print(r.run_id, r.pipeline, r.status)
```

## Role in orchestration pipeline

Every layer above depends on `db/`:

- **Events** → `event_bus.py` writes `EventLog` rows.
- **Orchestrator** → `dag.py` writes `RunAudit` rows.
- **Feature store** → `registry.py` writes `FeatureSnapshot`; `version_policy.py` writes `FeatureVersion`.
- **Ingestion** → `idempotency.py` reads/writes `IngestionSeen` + `IngestionDLQ`.
- **Steps** → model outputs land in `ForecastOutput`.
- **Reconciliation** → `actual_outcomes` + variance rows.

## Related

- Migrations: [db/migrations/](migrations/).
- Config section that drives this: `database:` in [config.yml](../config.yml).
