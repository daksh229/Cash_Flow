# feature_store/

Versioned, tenant-scoped feature store. Every S1–S7 module reads features through this layer (never from raw data directly).

## Files

| File | Purpose |
|------|---------|
| `registry.py` | `FeatureRegistry(feature_set)` with `write(df, entity_col, version?, tenant_id?)` and `read(version?, entity_ids?, tenant_id?)`. Auto-registers every write as a `draft` version and resolves reads to the `active` version by default. |
| `versioning.py` | Deterministic version strings. `make_version(reference_date, fingerprint)` → `"YYYY-MM-DD_abc12345"`. `current_version()` reads `global.reference_date` from config. |
| `version_policy.py` | State machine: `draft → active → frozen → retired`. `register()`, `promote(feature_set, version)`, `freeze(..., reason)`, `resolve_active_version()`, `stale_check(max_age_hours)`. |
| `__init__.py` | Re-exports `FeatureRegistry`, `make_version`, `current_version`, `register_version`, `promote`, `freeze`, `resolve_active_version`, `stale_check`. |

## Run individually

No CLI. Usage:

```python
import pandas as pd
from feature_store import FeatureRegistry, promote, resolve_active_version

reg = FeatureRegistry("customer_features")
v = reg.write(df, entity_col="customer_id")       # writes as 'draft'
promote("customer_features", v)                   # 'draft' -> 'active'
out = reg.read(entity_ids=["C1", "C2"])           # reads 'active' automatically
```

## Role in orchestration pipeline

- **Inbound**: [steps/feature_table.py](../steps/feature_table.py) writes via `FeatureRegistry.write(...)` after every nightly rebuild.
- **Outbound**: every ML module (S1, S2, Credit Risk) reads via `FeatureRegistry.read(...)`.
- **Policy hook**: after a model trains on a version, the training code should call `freeze(feature_set, version, reason="trained_by_<run_id>")` so the version is never deleted.

## Related

- Table: `feature_snapshots` + `feature_versions` in [db/models.py](../db/models.py).
- Tenant scoping via [security/tenant_context.py](../security/tenant_context.py).
- Unit tests: [tests/unit/test_feature_registry.py](../tests/unit/test_feature_registry.py).
