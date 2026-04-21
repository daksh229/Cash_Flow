# security/

Authentication, role-based access control, secret loading, and multi-tenant context.

## Files

| File | Purpose |
|------|---------|
| `auth.py` | HMAC-SHA256 signed bearer tokens. `issue_token(subject, roles, ttl_seconds)` + `verify_token(token)`. Uses `AUTH_SIGNING_KEY` secret. |
| `rbac.py` | Role enum (`VIEWER ⊂ ANALYST ⊂ ADMIN`) + FastAPI dependency `require_role(role)`. |
| `secrets.py` | Resolves secrets in order: env var → `.env` (if `python-dotenv` installed) → `/run/secrets/<name>`. |
| `tenant_context.py` | Request-scoped tenant selector via `contextvars`. `current_tenant()` + `tenant_scope(id)` context manager + `set_tenant(id)`. |
| `__init__.py` | Re-exports all of the above. |

## Run individually

No CLI. Issue a token for quick API testing:

```python
from security import issue_token
print(issue_token("alice", roles=["analyst"], ttl_seconds=3600))
```

Use the output as `Authorization: Bearer <token>` when hitting the API.

## Role in orchestration pipeline

- `tenant_context.current_tenant()` is called by [events/event_bus.py](../events/event_bus.py), [orchestrator/dag.py](../orchestrator/dag.py), [feature_store/registry.py](../feature_store/registry.py) so every DB write is tenant-scoped.
- `rbac.require_role(...)` gates API write endpoints in [app/routers/](../app/routers/).
- `secrets.get_secret(...)` is used by [ingestion/outbound.py](../ingestion/outbound.py) (signing Data Hub pushes) and [auth.py](auth.py) itself.

## Required secrets

| Name | Used by | Where to set |
|------|---------|--------------|
| `AUTH_SIGNING_KEY` | Bearer-token HMAC | env var or `/run/secrets/AUTH_SIGNING_KEY` |
| `DATA_HUB_SIGNING_KEY` | Inbound + outbound Data Hub HMAC | same |
| `CASHFLOW_DB_URL` (optional) | Overrides `database.url` in config | env var |
| `CASHFLOW_TENANT_ID` (optional) | Sets active tenant for batch jobs | env var |

## Related

- Used by every API router + the event/DAG layer.
- Config: `tenancy.default_tenant` + `tenancy.tenants` in [config.yml](../config.yml).
