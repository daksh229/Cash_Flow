# tests/

Three-tier test pyramid: **unit** (fast, isolated), **integration** (multi-module with an ephemeral DB), **regression** (metric-drift gate against committed baselines).

## Files

| Path | Purpose |
|------|---------|
| `conftest.py` | Shared fixtures. `tmp_db` swaps the DB engine to an ephemeral sqlite file per test + applies migrations. `reset_event_bus` clears subscribers between tests. `tmp_audit_paths` redirects JSONL writes. |
| `unit/` | Fast, module-scoped tests. See [unit/README.md](unit/README.md). |
| `integration/` | Cross-module tests that touch the DB. See [integration/README.md](integration/README.md). |
| `regression/` | Metric-drift gate. See [regression/README.md](regression/README.md). |
| `__init__.py` | Package marker. |

## Run individually

```bash
# Everything fast
pytest tests/unit -v

# Add integration (uses ephemeral sqlite per test, so still fast)
pytest tests/unit tests/integration -v

# Regression gate — skips until reports/*metrics*.json exist
pytest tests/regression -v

# All at once
pytest -v
```

Configuration: [pytest.ini](../pytest.ini) declares testpaths + markers.

## Role in orchestration pipeline

Tests are **not** part of the runtime pipeline. They run in CI or pre-commit:

- Unit + integration: run on every PR and before every deploy. Must be green.
- Regression: run after a training run produces new metrics JSON. Fails if any model regresses beyond tolerance.

Fixtures deliberately use **ephemeral sqlite** (not the project's `Data/cashflow.db`) so tests never pollute or depend on real data.

## Related

- Config: [pytest.ini](../pytest.ini).
- Smoke tests (manual, not in this folder): [smoke_test_v2_1.py](../smoke_test_v2_1.py) exercises v2.1 additions end-to-end.
