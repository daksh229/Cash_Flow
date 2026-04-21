# deploy/

Container + orchestration artefacts for running the platform outside a dev laptop.

## Files

| File | Purpose |
|------|---------|
| `Dockerfile` | Python 3.11-slim base. Installs build-essential + libgomp1 (for LightGBM). Runs as non-root user (uid 1000). Healthcheck hits `/health/live`. Default CMD runs `uvicorn app.api:app`. |
| `docker-compose.yml` | 3 services: `db` (Postgres 16), `api` (FastAPI), `frontend` (Streamlit). Docker secrets mount `AUTH_SIGNING_KEY`, `DB_PASSWORD`. API waits on DB health. |
| `.dockerignore` | Excludes venv, caches, mlruns, Data/, sample_data.zip, tests, secrets from build context. |
| `k8s/` | Kubernetes manifests for production. See [k8s/README.md](k8s/README.md). |

## Run individually

### Build the image
```bash
cd deploy
docker build -t cashflow/api:latest -f Dockerfile ..
```

### Full stack via Compose
```bash
cd deploy
mkdir -p secrets
echo "change-me" > secrets/auth_signing_key.txt
echo "change-me" > secrets/db_password.txt
echo "change-me" > secrets/data_hub_signing_key.txt
docker-compose up --build
```

Services:
- Postgres: `localhost:5432` (user `cashflow` / db `cashflow`)
- API: `http://localhost:8000` (docs at `/docs`)
- Frontend: `http://localhost:8501`

Tear down:
```bash
docker-compose down -v         # -v also removes the pgdata volume
```

## Role in orchestration pipeline

Not part of the pipeline — these files describe how to **run** the pipeline elsewhere.

Inside a container, the DAG still needs the DB migrations applied:

```bash
docker-compose exec api python -m db.migrations.001_initial_schema
docker-compose exec api python -m db.migrations.002_tenant_and_new_tables
docker-compose exec api python -m db.migrations.003_partials_improvements
```

Then trigger a run:

```bash
docker-compose exec api python -m orchestrator.scheduler
```

## Required secrets

| Name | Used by | Where |
|------|---------|-------|
| `AUTH_SIGNING_KEY` | [security/auth.py](../security/auth.py) | `deploy/secrets/auth_signing_key.txt` |
| `DB_PASSWORD` | Postgres + API `CASHFLOW_DB_URL` | `deploy/secrets/db_password.txt` |
| `DATA_HUB_SIGNING_KEY` | [ingestion/](../ingestion/) | `deploy/secrets/data_hub_signing_key.txt` |

Compose mounts them at `/run/secrets/<name>` — [security/secrets.py](../security/secrets.py) resolves them automatically.

## Related

- App: [app/](../app/).
- Secrets: [security/secrets.py](../security/secrets.py).
- K8s: [deploy/k8s/](k8s/).
