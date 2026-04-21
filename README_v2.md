# Cash Flow Forecasting Platform — v2

A production-grade cash flow forecasting platform with ML prediction models, rule-based forecasting engines, a treasury recommendation engine, and a full operational spine: persisted store, DAG orchestration, events, audit, monitoring, security, multi-tenancy, Data Hub integration, reconciliation and feedback learning.

Built from **CashFlow Solution Design Document (SDD v17)** and the client Q&A with Nikunj.

---

## Table of Contents

1. [What's New](#1-whats-new)
2. [System Overview](#2-system-overview)
3. [Full Project Structure](#3-full-project-structure)
4. [Prerequisites](#4-prerequisites)
5. [Run Flow — Step by Step](#5-run-flow--step-by-step)
6. [Configuration Reference](#6-configuration-reference)
7. [Module Architecture (S1–S7 + RE)](#7-module-architecture-s1s7--re)
8. [Multi-Tenancy](#8-multi-tenancy)
9. [Cold-Start / Prior / Model Selector / Model Registry](#9-cold-start--prior--model-selector--model-registry)
10. [Non-PO Expense Capture](#10-non-po-expense-capture)
11. [Data Hub Integration (Inbound + Outbound)](#11-data-hub-integration-inbound--outbound)
12. [Reconciliation & Cash-Accuracy KPI](#12-reconciliation--cash-accuracy-kpi)
13. [Recommendation Engine Feedback Loop](#13-recommendation-engine-feedback-loop)
14. [Feature Version Policy](#14-feature-version-policy)
15. [Event-Driven Re-scoring + Volume-Triggered Retraining](#15-event-driven-re-scoring--volume-triggered-retraining)
16. [Orchestration & DAG](#16-orchestration--dag)
17. [Persisted Data Layer](#17-persisted-data-layer)
18. [Audit & Lineage](#18-audit--lineage)
19. [Error Handling](#19-error-handling)
20. [Security & RBAC](#20-security--rbac)
21. [Monitoring & Observability](#21-monitoring--observability)
22. [Testing](#22-testing)
23. [Deployment](#23-deployment)
24. [API Reference](#24-api-reference)
25. [Troubleshooting](#25-troubleshooting)

---

## 1. What's New

### v2 (infrastructure rollup)
v1 was a working MVP. v2 added the operational spine that turns it into a production system:

| # | Area | Summary |
|---|------|---------|
| 1 | Persisted data layer | SQLAlchemy: feature_snapshots, forecast_outputs, run_audit, event_log |
| 2 | Orchestration (DAG) | Dependency graph, partial re-runs, upstream-failure skipping |
| 3 | Events | In-process bus + DB persistence + replay |
| 4 | Audit & lineage | JSONL audit trail, dataset lineage with git rev + config hash |
| 5 | Error handling | Domain hierarchy, retry with backoff, circuit breaker |
| 6 | Testing | Unit + integration + regression baselines + ephemeral sqlite fixtures |
| 7 | Security & deploy | HMAC tokens, RBAC roles, secrets loader, Dockerfile, compose, k8s |
| 8 | Monitoring | Prometheus metrics, health/ready probes, JSON logging |
| 9 | S2 treasury logic | Liquidity gate, discount capture, credit-line draw |
| 10 | S7 normalise/trust/dedup/audit | Canonical events, source trust scoring, bucket-based dedup |

### v2.1 (client Q&A follow-through)
After the Q&A with Nikunj, the following gaps were closed:

| # | Client ask | What's new |
|---|-----------|------------|
| 1 | Multi-entity deployment (2-3 tenants) | `tenant_id` on every table, tenant context-var, scoped registries |
| 2 | Core unlock: cold-start + per-customer variance | 3-level hierarchical prior (customer / segment / global) with empirical-Bayes shrinkage |
| 3 | LightGBM→RF auto-rollback on degradation | Model selector + model registry with active/shadow/retired states |
| 4 | Non-PO expense capture | DB table + FastAPI router + Streamlit form |
| 5 | Data Hub event-push ingestion | HMAC-signed webhook + bulk + DLQ + idempotency + JSONL replay |
| 6 | Forecast ↔ actual reconciliation | `actual_outcomes` + per-run variance CSV + summary JSON |
| 7 | Cash-accuracy weighted KPI | Composite score `0.7·cash + 0.3·days`, exposed via Prometheus |
| 8 | Volume-triggered retraining | Event-counter-driven partial DAG runs |
| 9 | Feature-version freeze/stale policy | `feature_versions` state machine, draft → active → frozen → retired |
| 10 | RE weight learning | `recommendation_feedback` + NNLS weight tuner |
| 11 | Outbound publishing to Data Hub | HMAC-signed POST with local JSONL fallback |
| 12 | Thin-data analysis in S1 | Reusable `steps/shared/thin_data.py` wired into S1 training |

---

## 2. System Overview

### 2.1 Module map

| Module | Type | Method | Purpose |
|--------|------|--------|---------|
| **S1** | ML prediction | LightGBM + RF | `days_to_pay` for AR invoices |
| **S2** | ML prediction | LightGBM + RF | Payment timing for AP bills |
| **Credit Risk** | ML classification | LightGBM + RF | LOW / MEDIUM / HIGH risk bands |
| **S3** | Rule-based | Deterministic | WIP/project-milestone billing forecast |
| **S4** | Rule-based | Cohort matching | Sales-pipeline cash forecast |
| **S5** | Rule-based | Scheduling | Contingent inflows (loans, grants, refunds) |
| **S6** | Rule-based | Category scheduling | Expense forecast (incl. non-PO captures) |
| **S7** | Aggregation | Normalise + trust + dedup | Unified daily cash position |
| **RE** | Scoring + ranking | Multi-lever + feedback | Treasury recommendations |

### 2.2 End-to-end data flow

```
 Data Hub (external)
    │ push events (HMAC-signed)
    ▼
 ingestion/data_hub_adapter  ──► DLQ on failure
        │ idempotent
        ▼
 Event Bus (persisted)  ──► Volume Trigger ──► partial DAG run
        │
        ▼
 Feature Store (versioned, tenant-scoped)
        │
        ├─ S1/S2/Credit Risk (ML, with prior + model selector)
        ├─ S3/S4/S5/S6 (rule-based)
        │
        ▼
 S7 Cash Aggregation (normalise → trust → dedup → audit)
        │
        ▼
 Recommendation Engine  ──► user accept/reject ──► feedback store
        │                                               │
        ▼                                               ▼
 API / Streamlit / Prometheus                  Weight Tuner (proposal)

 Reconciliation  ◄── actual_outcomes (from Data Hub or manual)
        │
        ▼
 Cash-Accuracy KPI   ──► Prometheus + baselines regression gate
        │
        ▼
 Outbound Publisher  ──► Data Hub (forecast.published)
```

---

## 3. Full Project Structure

```
Project-1/
├── main.py                              # v1 linear entry point
├── config.yml                           # master config: db, tenancy, kpi, retraining
├── requirements.txt
├── pytest.ini
├── README.md / README_v2.md / STRUCTURE.md
├── CashFlow_SDD_v17-20032026.docx
├── Model_InputOutput_Mapping.md
├── Vaibhav Q&A.xlsx
│
├── config/                              # per-model YAML (+ cold_start, model_selector)
│
├── steps/                               # core pipeline logic
│   ├── feature_table.py
│   ├── s1_ar_prediction/ …              # + thin-data wiring in model_training.py
│   ├── s2_ap_prediction/
│   │   ├── liquidity_gate.py
│   │   └── treasury_logic.py
│   ├── credit_risk/
│   ├── s3_wip_forecast/ … s6_expense_forecast/
│   ├── s7_cash_aggregation/
│   │   ├── normalization.py
│   │   ├── trust_scoring.py
│   │   ├── dedup_engine.py
│   │   └── audit_model.py
│   ├── recommendation_engine/
│   │   ├── input_format.py forecast_engine.py output.py
│   │   ├── feedback_store.py            [v2.1]
│   │   └── weight_tuner.py              [v2.1]
│   └── shared/                          [v2.1]
│       ├── cold_start.py                # hierarchical prior (core unlock)
│       ├── model_selector.py            # per-call routing
│       ├── model_registry.py            # active/shadow/retired promotion
│       └── thin_data.py                 # reusable thin-data analyser
│
├── app/                                 # web layer
│   ├── api.py   frontend.py
│   ├── routers/                         [v2.1]
│   │   ├── non_po_expenses.py
│   │   └── recommendations.py
│   └── pages/
│       └── non_po_expense_form.py       # Streamlit form
│
├── db/
│   ├── connection.py schema.py models.py
│   └── migrations/
│       ├── 001_initial_schema.py
│       ├── 002_tenant_and_new_tables.py [v2.1]
│       └── 003_partials_improvements.py [v2.1]
│
├── feature_store/
│   ├── registry.py   versioning.py
│   └── version_policy.py                [v2.1] draft→active→frozen→retired
│
├── orchestrator/
│   ├── dag.py   scheduler.py   dependencies.py
│   └── volume_trigger.py                [v2.1]
│
├── events/
│   └── event_bus.py  triggers.py  listeners.py
│
├── audit/
│   └── audit_logger.py  lineage_tracker.py
│
├── core/
│   └── exceptions.py  retry.py  circuit_breaker.py
│
├── security/
│   ├── auth.py  rbac.py  secrets.py
│   └── tenant_context.py                [v2.1]
│
├── monitoring/
│   ├── metrics.py  health.py  logging_config.py
│   └── cash_accuracy.py                 [v2.1]
│
├── ingestion/                           [v2.1]
│   ├── schema_mapper.py
│   ├── data_hub_adapter.py              # webhook + bulk + DLQ replay
│   ├── idempotency.py                   # was_seen / mark_seen / to_dlq
│   └── outbound.py                      # forecast.published → Data Hub
│
├── reconciliation/                      [v2.1]
│   └── reconcile.py                     # ForecastOutput ⋈ ActualOutcome
│
├── deploy/                              # Dockerfile, compose, k8s
│
├── tests/
│   ├── conftest.py  unit/  integration/  regression/
│
├── pipeline/                            # v1 linear runners
├── sample_data/                         # generators
├── mlruns/  models/  reports/  Data/    # runtime
```

---

## 4. Prerequisites

- **Python** 3.11+
- **Git**
- **Optional**: Docker + Docker Compose, Postgres 16+ (for non-SQLite DB)

---

## 5. Run Flow — Step by Step

### 5.1 First-time setup

```bash
cd Project-1

python -m venv venv
source venv/bin/activate          # Linux/Mac
venv\Scripts\activate             # Windows

pip install -r requirements.txt

# Apply all migrations in order
python -m db.migrations.001_initial_schema
python -m db.migrations.002_tenant_and_new_tables
python -m db.migrations.003_partials_improvements

# Generate sample data (one-time)
python sample_data/generate_raw_tables.py
python sample_data/generate_project_milestones.py
python sample_data/generate_crm_pipeline.py
python sample_data/generate_s5_s6_data.py
```

### 5.2 Mode A — Quick run (v1 linear)
```bash
python main.py
```

### 5.3 Mode B — Production run (DAG, tenant-aware)
```bash
CASHFLOW_TENANT_ID=entity_alpha python -m orchestrator.scheduler
```

### 5.4 Mode C — Single-module run
```bash
python pipeline/run_s1_ar_prediction.py
python pipeline/run_s7_cash_aggregation.py
```

### 5.5 Mode D — Event-triggered re-run
```python
from events.event_bus import bus
from events.triggers import EventName
from events.listeners import register_default_listeners
from orchestrator.volume_trigger import register_volume_listeners

register_default_listeners()
register_volume_listeners()
bus.emit(EventName.INVOICE_CREATED, {"invoice_id": "INV-123"})
```

### 5.6 Mode E — Data Hub webhook
```bash
# Data Hub POSTs JSON envelopes to /ingest/event (HMAC-signed)
# Or bulk replay from a JSONL file:
python -m ingestion.data_hub_adapter --file backfill_2026_04.jsonl
```

### 5.7 Reconciliation + KPI
```bash
# After a run, feed in realised cash events (via API or bulk)
python -m reconciliation.reconcile --tenant entity_alpha
python -m monitoring.cash_accuracy --tenant entity_alpha
```

### 5.8 Web application
```bash
# Terminal 1 — FastAPI
python app/api.py                 # http://localhost:8000  (docs at /docs)

# Terminal 2 — Streamlit main dashboard
streamlit run app/frontend.py     # http://localhost:8501

# Terminal 3 — Non-PO capture form
streamlit run app/pages/non_po_expense_form.py
```

### 5.9 Tests
```bash
pytest tests/unit tests/integration -v
pytest tests/regression -v              # after reports/<model>*metrics*.json exists
```

### 5.10 Docker (single command)
```bash
cd deploy
echo "change-me" > secrets/auth_signing_key.txt
echo "change-me" > secrets/db_password.txt
echo "change-me" > secrets/data_hub_signing_key.txt
docker-compose up --build
```

---

## 6. Configuration Reference

### 6.1 Master — `config.yml`

| Section | Purpose |
|---------|---------|
| `global` | random seed, log level, data paths, reference date |
| `database` | backend (sqlite/postgres), url, pool size |
| **`tenancy`** | default_tenant + list of active tenants |
| `mlflow` | tracking URI, experiment prefix |
| `feature_table` | on/off flag |
| `models` | ordered list of models to run |
| `training` | shared training defaults |
| **`kpi`** | `cash_weight`, `days_weight`, `mae_days_target` |
| **`retraining`** | per-model `new_rows_threshold` for volume triggers |

### 6.2 Per-model — `config/*.yml`

| File | What it drives |
|------|----------------|
| `s1_ar_prediction.yml` | features, hyperparams, split, eval, **thin_data_threshold**, **cold_start**, **model_selector** |
| `s2_ap_prediction.yml` | + `liquidity_gate`, `treasury`, same prior/selector blocks |
| `credit_risk.yml` | classification + imbalance |
| `s3..s6.yml` | module-specific rules |
| `s7_cash_aggregation.yml` | source trust, dedup window, opening balance |
| `recommendation_engine.yml` | scoring weights, levers, constraints (feedback tuner writes proposals) |

---

## 7. Module Architecture (S1–S7 + RE)

### S1 / S2 / Credit Risk (ML)
4-stage pipeline: `input_format` → `preprocessing` → `model_training` → `evaluate`.
S1 and S2 training now log thin-data vs rich-data MAE separately via [steps/shared/thin_data.py](steps/shared/thin_data.py).

### S3 / S4 / S5 / S6 (rule-based)
3-stage pipeline: `input_format` → `forecast_engine` → `output`. S6 also reads active rows from `non_po_expenses`.

### S2 treasury extensions
- [steps/s2_ap_prediction/liquidity_gate.py](steps/s2_ap_prediction/liquidity_gate.py) — pay / defer / partial decisions.
- [steps/s2_ap_prediction/treasury_logic.py](steps/s2_ap_prediction/treasury_logic.py) — discounts, credit-line, cheapest-to-defer.

### S7 extensions
- [normalization.py](steps/s7_cash_aggregation/normalization.py) — canonical event schema.
- [trust_scoring.py](steps/s7_cash_aggregation/trust_scoring.py) — `trust = source_baseline × confidence × recent_metric_bump`.
- [dedup_engine.py](steps/s7_cash_aggregation/dedup_engine.py) — bucket by (entity, amount, date-window); highest trust wins.
- [audit_model.py](steps/s7_cash_aggregation/audit_model.py) — per-run summary + lineage edge.

### RE extensions
- [feedback_store.py](steps/recommendation_engine/feedback_store.py) — capture accept/reject + realised impact.
- [weight_tuner.py](steps/recommendation_engine/weight_tuner.py) — NNLS-based proposal writer.

---

## 8. Multi-Tenancy

Every DB row carries `tenant_id`. The active tenant for a given code path is resolved via [security/tenant_context.py](security/tenant_context.py):

```python
from security.tenant_context import tenant_scope, current_tenant

with tenant_scope("entity_alpha"):
    reg = FeatureRegistry("customer_features")
    reg.write(df, entity_col="customer_id")   # automatically tenant-scoped
```

Sources of tenant identity, in order:
1. `tenant_scope(...)` context manager (in-process scope).
2. `X-Tenant-Id` request header (API).
3. `CASHFLOW_TENANT_ID` env var (batch / CLI).
4. Literal `"default"` fallback.

All tenant-aware tables: `feature_snapshots`, `forecast_outputs`, `run_audit`, `event_log`, `non_po_expenses`, `actual_outcomes`, `feature_versions`, `recommendation_feedback`, `model_registry`, `ingestion_dlq`, `ingestion_seen`.

---

## 9. Cold-Start / Prior / Model Selector / Model Registry

This is the **"core architectural unlock"** Nikunj flagged in Q8.

### Hierarchical Prior ([steps/shared/cold_start.py](steps/shared/cold_start.py))

```
predicted = w_customer · µ_customer + w_segment · µ_segment + w_global · µ_global
w_customer = n_customer / (n_customer + τ)    if n_customer ≥ min_customer_n
```

Segment key = (`risk_segment`, `amount_bucket`, `season`). Shrinkage parameter `τ` is tunable in config (`cold_start.tau`).

Fit during S1/S2 training; persists to `models/cold_start_prior.pkl`.

### Model Selector ([steps/shared/model_selector.py](steps/shared/model_selector.py))

At serve time, picks one of `primary` (LGB) / `baseline` (RF) / `prior` per prediction. Inputs: recent metric history, per-entity row count, config thresholds. Honours the active variant in the **model registry** if one is set.

### Model Registry ([steps/shared/model_registry.py](steps/shared/model_registry.py))

Per-(tenant, model_key, variant) promotion state: `active` | `shadow` | `retired`. Auto-rollback flow: evaluator detects degradation → `demote("primary")` → `promote("baseline")` → selector sees new state on next call. `shadow` variants are used for champion/challenger evaluations without serving.

---

## 10. Non-PO Expense Capture

Operational expenses (legal fees, consultancy, ad-hoc travel, ads) often never hit a PO — Nikunj confirmed in Q2 that a UI is needed.

- **DB**: `non_po_expenses` table (tenant-scoped).
- **API**: [app/routers/non_po_expenses.py](app/routers/non_po_expenses.py)
  - `POST /expenses/non-po` — submit (emits `bill.created` so S6 re-scores).
  - `GET /expenses/non-po` — list active.
  - `DELETE /expenses/non-po/{id}` — deactivate.
- **UI**: [app/pages/non_po_expense_form.py](app/pages/non_po_expense_form.py) (standalone Streamlit page).

---

## 11. Data Hub Integration (Inbound + Outbound)

### Inbound ([ingestion/data_hub_adapter.py](ingestion/data_hub_adapter.py))

Data Hub pushes a canonical envelope:
```json
{
  "envelope_id": "uuid",
  "type": "invoice.paid",
  "tenant_id": "entity_alpha",
  "occurred_at": "2026-04-21T10:15:00Z",
  "data": { ... }
}
```

Flow: HMAC-verify → duplicate check ([ingestion/idempotency.py](ingestion/idempotency.py)) → map to internal event name ([ingestion/schema_mapper.py](ingestion/schema_mapper.py)) → emit on bus. Failures go to the **DLQ** (`ingestion_dlq` table).

Endpoints:
- `POST /ingest/event` — real-time webhook.
- `POST /ingest/bulk` — JSON array for backfills.
- `POST /ingest/dlq/replay?reason=&limit=` — re-submit DLQ rows.
- CLI: `python -m ingestion.data_hub_adapter --file backfill.jsonl`

### Outbound ([ingestion/outbound.py](ingestion/outbound.py))

Subscribes to `forecast.published`. For each event: HMAC-signed POST to `$DATA_HUB_URL`; falls back to `reports/outbound/<date>.jsonl` when the URL isn't configured or the network fails.

Enable with:
```python
from ingestion import register_outbound_publisher
register_outbound_publisher()
```

---

## 12. Reconciliation & Cash-Accuracy KPI

### Reconciliation ([reconciliation/reconcile.py](reconciliation/reconcile.py))

Joins `forecast_outputs` against `actual_outcomes` on `(tenant_id, reference_id)`; writes:
- `reports/reconciliation/<tenant>_<run>.csv` — per-row variance.
- `reports/reconciliation/<tenant>_<run>.summary.json` — `match_rate`, `mae_days`, `bias_days`, `mape_amount`.

Record an actual:
```python
from reconciliation import record_actual
record_actual("INV-123", source_type="AR",
              actual_date="2026-05-02", actual_amount=125_000)
```

### KPI ([monitoring/cash_accuracy.py](monitoring/cash_accuracy.py))

Nikunj's primary metric (Q7):
```
cash_accuracy  = (1 - clamp(mape_amount, 0, 1)) · 100
days_accuracy  = max(0, 1 - mae_days / mae_days_target) · 100
kpi            = cash_weight · cash_accuracy + days_weight · days_accuracy
```

Defaults `cash_weight = 0.7`, `days_weight = 0.3`, `mae_days_target = 10` (override in `config.yml → kpi:`). Result is exported to Prometheus as `cashflow_model_mae{model="cash_kpi:<tenant>"}` and gated in [tests/regression/baselines.yml](tests/regression/baselines.yml).

---

## 13. Recommendation Engine Feedback Loop

Q11: RE weights start as placeholders; the feedback loop tunes them.

1. Engine produces a recommendation with `score_components` ({cash_improvement, risk_reduction, target_alignment, feasibility}).
2. User submits `POST /recommendations/feedback` with `action = accepted|rejected|ignored`.
3. Reconciliation (or a manual API call `POST /recommendations/{id}/realised`) attaches the realised cash impact.
4. `python -m steps.recommendation_engine.weight_tuner --tenant <t>` fits a non-negative least-squares proposal and writes `reports/re_weights/<tenant>.json`.
5. Operator reviews the proposal and promotes it into `config/recommendation_engine.yml`.

The tuner **never** promotes weights automatically — deliberate to avoid oscillation in the first weeks of data.

---

## 14. Feature Version Policy

Q4 asked what happens to in-flight predictions when feature logic changes. Answer: the version state machine.

```
draft ── promote() ──► active ── freeze(reason) ──► frozen
                         │
                         └─ promote(new) ──► retired
```

- `FeatureRegistry.write()` auto-registers the new version as **draft**.
- `FeatureRegistry.read()` now resolves to the **active** version by default — old predictions keep reading their pinned version.
- `freeze(version, reason)` is called whenever a trained model or published forecast depends on a version; frozen rows are retained forever for reproducibility.
- `stale_check(feature_set, max_age_hours)` flags versions that should be rebuilt.

API: [feature_store/version_policy.py](feature_store/version_policy.py) re-exported from `feature_store`.

---

## 15. Event-Driven Re-scoring + Volume-Triggered Retraining

### Event-driven (per-record)
| Event | Default listener |
|-------|------------------|
| `invoice.{created,paid,updated}` | re-run `s1_ar_prediction` subgraph |
| `bill.{created,paid,updated}` | re-run `s2_ap_prediction` subgraph |
| `customer.updated` / `vendor.updated` | rebuild `feature_table` (cascades) |
| `forecast.published` | outbound publisher → Data Hub |

### Volume-triggered retraining ([orchestrator/volume_trigger.py](orchestrator/volume_trigger.py))

Counts ingestion events per `(tenant, model_key)`. When the counter crosses `retraining.<model>.new_rows_threshold` in `config.yml`, fires `Scheduler.run_subgraph([model_key])` and resets. Addresses Q6 ("volume-based, not periodic").

```python
from orchestrator.volume_trigger import register_volume_listeners
register_volume_listeners()
```

---

## 16. Orchestration & DAG

- [orchestrator/dependencies.py](orchestrator/dependencies.py) — declares edges.
- [orchestrator/dag.py](orchestrator/dag.py) — topological executor; stamps `run_audit` with `tenant_id`; skips downstreams when upstream fails.
- [orchestrator/scheduler.py](orchestrator/scheduler.py) — `run_full()` + `run_subgraph(keys)`.

Partial re-runs honour the dependency closure automatically — re-running `feature_table` cascades to every consumer.

---

## 17. Persisted Data Layer

ORM tables in [db/models.py](db/models.py):

**v2 core**
| Table | Role |
|-------|------|
| `feature_snapshots` | versioned feature rows |
| `forecast_outputs` | unified S1–S7 + RE outputs (with `reference_id`) |
| `run_audit` | one row per DAG run |
| `event_log` | event-bus persistence |

**v2.1 additions**
| Table | Role |
|-------|------|
| `non_po_expenses` | manually-captured operational expenses |
| `actual_outcomes` | realised cash events from ERP/Data Hub |
| `feature_versions` | version state machine |
| `recommendation_feedback` | user action + realised impact on recs |
| `model_registry` | per-(tenant, model, variant) serving state |
| `ingestion_dlq` | dead-letter queue |
| `ingestion_seen` | envelope-id idempotency |

Feature access via [feature_store/registry.py](feature_store/registry.py):
```python
from feature_store import FeatureRegistry
reg = FeatureRegistry("customer_features")
reg.write(df, entity_col="customer_id")   # auto-registered as draft
out = reg.read(entity_ids=["C1", "C2"])    # reads active version
```

---

## 18. Audit & Lineage

- [audit/audit_logger.py](audit/audit_logger.py) — JSONL append to `reports/audit.jsonl`.
- [audit/lineage_tracker.py](audit/lineage_tracker.py) — `reports/lineage.jsonl` with `git_rev` + `config_hash`. `lineage.trace(output)` walks backwards.

---

## 19. Error Handling

Hierarchy in [core/exceptions.py](core/exceptions.py); decorators in [core/retry.py](core/retry.py) and [core/circuit_breaker.py](core/circuit_breaker.py).

| Exception | DAG behaviour |
|-----------|---------------|
| `ConfigError` / `DataValidationError` | fail-fast |
| `UpstreamDataMissing` | skip + re-queue |
| `ModelTrainingError` | fail, recorded in `run_audit` |
| `ExternalServiceError` | retryable with backoff |

---

## 20. Security & RBAC

- [security/auth.py](security/auth.py) — HMAC bearer tokens.
- [security/rbac.py](security/rbac.py) — `VIEWER ⊂ ANALYST ⊂ ADMIN`, FastAPI dependency.
- [security/secrets.py](security/secrets.py) — env → `.env` → `/run/secrets/<name>`.
- [security/tenant_context.py](security/tenant_context.py) — request-scoped tenant selection.

Required secrets: `AUTH_SIGNING_KEY`, `DATA_HUB_SIGNING_KEY`, optional `CASHFLOW_DB_URL`.

---

## 21. Monitoring & Observability

Endpoints (via [monitoring/health.py::register_health_routes()](monitoring/health.py)):

| Endpoint | Purpose |
|----------|---------|
| `GET /health/live` | liveness |
| `GET /health/ready` | DB-reachable readiness |
| `GET /metrics` | Prometheus scrape |

Metrics:
- `cashflow_runs_total{pipeline,status}`
- `cashflow_run_duration_seconds{pipeline}`
- `cashflow_model_mae{model}` (also `cash_kpi:<tenant>`)
- `cashflow_events_emitted_total{name}`
- `cashflow_db_errors_total`

Logging ([monitoring/logging_config.py](monitoring/logging_config.py)) — set `CASHFLOW_LOG_FORMAT=json` in prod.

---

## 22. Testing

```
tests/
├── conftest.py             # tmp_db, reset_event_bus, tmp_audit_paths
├── unit/                   # dag, bus, registry, retry, audit
├── integration/            # event → subgraph, dag + audit
└── regression/
    ├── baselines.yml       # includes cash_kpi baselines
    └── test_metric_baselines.py
```

---

## 23. Deployment

**Docker Compose:** [deploy/docker-compose.yml](deploy/docker-compose.yml) — Postgres + API + frontend, docker-secrets for `AUTH_SIGNING_KEY`, `DB_PASSWORD`, `DATA_HUB_SIGNING_KEY`.

**Kubernetes:** [deploy/k8s/deployment.yaml](deploy/k8s/deployment.yaml) — `runAsNonRoot`, `readOnlyRootFilesystem`, `drop: [ALL]` capabilities, probes on `/health/live`/`/health/ready`.

---

## 24. API Reference

All endpoints accept `Authorization: Bearer <token>` (from `security.auth.issue_token`) and an optional `X-Tenant-Id` header. `require_role()` gates write paths.

### Predictions / forecasts (existing)
| Endpoint | Purpose |
|----------|---------|
| `GET /predict/{s1,s2,credit_risk}/{id}` | lookup |
| `POST /predict/{s1,s2,credit_risk}/new` | new-entry |
| `GET /forecast/{s3..s7}/…` | module outputs |

### Recommendations
| Endpoint | Purpose |
|----------|---------|
| `GET /recommendations` | ranked list |
| `POST /recommendations/feedback` | user accept/reject |
| `POST /recommendations/{id}/realised` | attach realised impact |

### Non-PO expenses
| Endpoint | Purpose |
|----------|---------|
| `POST /expenses/non-po` | submit |
| `GET /expenses/non-po` | list active |
| `DELETE /expenses/non-po/{id}` | deactivate |

### Ingestion
| Endpoint | Purpose |
|----------|---------|
| `POST /ingest/event` | Data Hub webhook (HMAC) |
| `POST /ingest/bulk` | JSON array |
| `POST /ingest/dlq/replay` | re-submit DLQ rows |

### Monitoring
| Endpoint | Purpose |
|----------|---------|
| `GET /health/live` / `/health/ready` | probes |
| `GET /metrics` | Prometheus |

### Wiring (drop into `app/api.py`)
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

---

## 25. Troubleshooting

| Symptom | Likely cause | Fix |
|---------|--------------|-----|
| `ImportError: sqlalchemy` / `pytest` / `prometheus_client` | deps not installed | `pip install -r requirements.txt` |
| `no such table: feature_versions` | migration 003 not run | `python -m db.migrations.003_partials_improvements` |
| `KeyError: 'AUTH_SIGNING_KEY'` | secret missing | `export AUTH_SIGNING_KEY=...` or mount `/run/secrets/AUTH_SIGNING_KEY` |
| Webhook returns 401 | missing/wrong `X-Data-Hub-Signature` | ensure `DATA_HUB_SIGNING_KEY` matches Data Hub's |
| Feature reads return 0 rows | no active version yet | call `feature_store.promote(feature_set, version)` after first write |
| `model_selector` always picks `primary` | no registry entry | add `promote(model_key, "primary", version, ...)` after training, or rely on metric-based fallback |
| RE weight tuner says `skipped insufficient_data` | < 20 feedback rows | accumulate more accept/reject + realised impact rows |
| `reports/outbound/…jsonl` grows | `DATA_HUB_URL` not set | set env var to point at the live Data Hub ingress |
| Cycle detected at task `<x>` | bad edit to `dependencies.py` | remove the offending edge |
| Event handler failed, not retried | event sits in `event_log` with `processed=0` | `bus.replay_pending()` |
| Regression test failing | metric drifted below baseline | investigate, then update [baselines.yml](tests/regression/baselines.yml) if genuinely better |
| Duplicate envelopes processed twice | `envelope_id` missing in Data Hub push | ask Data Hub team to emit `envelope_id` (idempotency key) |

---

## Document References

- **SDD**: `CashFlow_SDD_v17-20032026.docx` — source of truth.
- **Q&A**: `Vaibhav Q&A.xlsx` — open-item answers from Nikunj.
- **Schema**: `Model_InputOutput_Mapping.md` — field-level I/O.
- **Structure**: `STRUCTURE.md` — v1 file tree.
