# db/migrations/

One script per schema change. Run in numerical order. Each script is idempotent (`create_all` + safe ALTERs).

## Files

| File | Adds |
|------|------|
| `001_initial_schema.py` | v2 core tables: `feature_snapshots`, `forecast_outputs`, `run_audit`, `event_log`. |
| `002_tenant_and_new_tables.py` | `tenant_id` column on the 4 core tables (via ALTER for existing DBs), plus new tables `non_po_expenses`, `actual_outcomes`. |
| `003_partials_improvements.py` | `feature_versions`, `recommendation_feedback`, `model_registry`, `ingestion_dlq`, `ingestion_seen`. |
| `__init__.py` | Empty package marker. |

## Run individually

Run in order, once per environment:

```bash
python -m db.migrations.001_initial_schema
python -m db.migrations.002_tenant_and_new_tables
python -m db.migrations.003_partials_improvements
```

Each prints the table list on success. Safe to re-run — `create_all` is a no-op for existing tables and the 002 ALTER guards against re-adding the column.

## Role in orchestration pipeline

Migrations run **before** the pipeline. The orchestrator assumes all tables exist. If a migration is missed, you'll see `no such table: <name>` at first write.

For production Postgres, swap these scripts for Alembic-managed migrations once the schema stabilises.

## Related

- Models: [db/models.py](../models.py).
- Connection: [db/connection.py](../connection.py).
