# Cash Flow Forecasting Platform — Approach & Architecture

A walk-through of **why** the platform is built the way it is, not just what's in it. Written for anyone reviewing the design — client, stakeholder, or a new engineer on the team — before they read the code.

Companion documents:
- [README_v2.md](README_v2.md) — detailed usage + API reference
- [README_FLOWS.md](README_FLOWS.md) — file-by-file interconnection diagrams + 3 end-to-end scenarios
- [STRUCTURE.md](STRUCTURE.md) — original file tree

---

## 1. Problem Statement

From the **CashFlow Solution Design Document (SDD v17)**:

> Treasury teams need a single, trusted, forward-looking view of cash — across receivables, payables, projects, pipeline, contingent inflows, and expenses — that updates when reality changes and suggests specific, explainable actions. Existing setups hold the pieces in separate spreadsheets; nobody has the composite view, and forecasts drift from reality within days.

Translated into engineering goals:

1. **Unified daily cash position** — one forecast table, not nine tabs in Excel.
2. **Event-reactive** — an invoice paid or a bill disputed should update the forecast within minutes, not at the next batch run.
3. **Explainable** — every forecasted cash event, every recommendation, must trace back to the raw data and rule/model that produced it.
4. **Production-grade** — multi-tenant, audited, monitored, secure, retrainable.
5. **Tunable** — the system learns from user accept/reject behaviour and from reconciliation with actuals.

---

## 2. Design Principles

Six principles drive every decision in the codebase.

### 2.1 Deterministic first, ML additive
Rule-based modules (S3 WIP, S4 pipeline, S5 contingent, S6 expense, plus S7 aggregation and the recommendation engine) produce the baseline forecast. ML modules (S1 AR, S2 AP, Credit Risk) **adjust** it. This guarantees the system always has a fallback and never hides behind a black box.

### 2.2 Feature store is the only source of truth
Every model reads from the same versioned feature tables (customer, invoice, vendor, bill, project, expense). No module re-computes features from raw data on its own. Retraining, replay, and multi-tenant scoping all depend on this invariant.

### 2.3 Events, not cron
Business truth changes event by event: an invoice gets paid, a bill gets approved, a customer profile gets updated. The platform treats these as first-class inputs. Cron-style batch runs are layered **on top** of events for daily consolidation — not the other way around.

### 2.4 Everything tenant-scoped
The client runs multiple entities under one deployment. Every DB row carries `tenant_id`. No data-leak risk between tenants is possible at the query layer.

### 2.5 Audit + lineage are non-negotiable
Every run writes a `run_audit` row. Every dataset writes a lineage edge with `git_rev` and `config_hash`. Every event is persisted in `event_log` before dispatch. Re-running exactly the same pipeline on exactly the same data must produce exactly the same answer — and prove it.

### 2.6 Config-driven
All tunable parameters (hyperparameters, thresholds, scoring weights, trust baselines, KPI weights) live in YAML. Changing behaviour is a config change + a new run, not a code change.

---

## 3. Architecture in Layers

The platform is five concentric layers. Lower layers are dependencies of higher layers; higher layers never bypass lower ones.

```
┌──────────────────────────────────────────────────────────────┐
│ 5. Presentation                                              │
│    app/api.py  •  app/frontend.py  •  app/routers/*          │
│    monitoring/health.py  (/health, /metrics)                 │
├──────────────────────────────────────────────────────────────┤
│ 4. Domain logic                                              │
│    steps/s1..s7/*  •  steps/recommendation_engine/*          │
│    steps/shared/* (cold_start, model_selector, model_reg)    │
│    reconciliation/*  •  monitoring/cash_accuracy.py          │
├──────────────────────────────────────────────────────────────┤
│ 3. Orchestration                                             │
│    orchestrator/dag.py  scheduler.py  dependencies.py        │
│    orchestrator/volume_trigger.py                            │
│    events/event_bus.py  listeners.py  triggers.py            │
├──────────────────────────────────────────────────────────────┤
│ 2. Integration                                               │
│    ingestion/data_hub_adapter.py  schema_mapper.py           │
│    ingestion/idempotency.py  outbound.py                     │
├──────────────────────────────────────────────────────────────┤
│ 1. Infrastructure                                            │
│    db/*  feature_store/*  audit/*  core/*  security/*        │
│    monitoring/metrics.py  logging_config.py                  │
└──────────────────────────────────────────────────────────────┘
```

### What each layer owns

| Layer | Responsibility | Examples |
|-------|----------------|----------|
| 1. Infrastructure | Persistence, auth, logging, retries, tenant scoping | SQLAlchemy models, HMAC tokens, retry decorator |
| 2. Integration | Talks to the outside world | Data Hub webhook, outbound publisher |
| 3. Orchestration | Decides what runs, when, in what order | DAG, event bus, volume trigger |
| 4. Domain | The actual financial forecasting + recommendations | S1–S7, RE, reconciliation |
| 5. Presentation | How humans and external systems consume outputs | FastAPI routes, Streamlit pages, Prometheus endpoint |

---

## 4. Module Map

Nine domain modules, organised into three families.

### ML prediction (S1, S2, Credit Risk)
Hybrid LightGBM + Random Forest with a shared **hierarchical prior** for cold-start and thin-data entities. The prior blends customer-level / segment-level / global-level statistics using empirical-Bayes shrinkage. A **model selector** picks primary / baseline / prior per call, honouring promotion state in the model registry.

### Rule-based forecast (S3, S4, S5, S6)
Deterministic scheduling logic driven by milestone rules, cohort statistics, approval status, or expense categories. No training loop. Outputs merge into the same canonical event schema as ML modules.

### Aggregation + recommendations (S7, RE)
S7 normalises all upstream outputs, applies trust scoring (blending config baselines with recent model metrics), deduplicates overlapping events, and emits the unified cash position. RE scores recommendations against this position using four dimensions (cash improvement, risk reduction, target alignment, feasibility). A feedback loop captures user accept/reject actions and adjusts scoring weights over time.

---

## 5. Key Decisions & Why

These are the choices that shaped the platform most, with the reasoning behind each.

### 5.1 Hierarchical prior instead of "just retrain more data"
The client confirmed launch volume is ~1,500–3,000 records with a meaningful share of customers under 10 invoices. Pure ML would overfit the rich-data customers and fail the thin-data ones. A prior that blends `w_customer · µ_customer + w_segment · µ_segment + w_global · µ_global` with Empirical-Bayes shrinkage:
- Works for **cold-start** customers (w_customer = 0, falls back to segment/global).
- Captures **seasonal + amount + dispute** variance via the segment key.
- Becomes a **feature** for the ML models so they learn to deviate from the prior with confidence — not to ignore it.

This is the "core architectural unlock" that was flagged in the Q&A.

### 5.2 Event bus with DB persistence, not Kafka
Kafka adds operational burden without yet adding value at this scale. The in-process bus persists every emit to `event_log` so replay + audit are possible. Swap-in of Kafka (or SNS/SQS) later is a single-adapter change.

### 5.3 SQLite for dev, Postgres for prod
One-line config switch. Both paths are tested. SQLite makes the test suite fast and the client demo one-command-startable. Postgres scales when real traffic arrives.

### 5.4 DAG orchestrator, not a linear runner
The v1 linear `main.py` breaks the moment one module fails — every downstream task runs on stale data. The DAG:
- Computes a topological order from an explicit dependency map.
- Marks downstream tasks as **skipped** when an upstream fails, instead of corrupting their outputs.
- Allows **partial re-runs** (`run_subgraph`) when an event updates only a slice of the graph.

### 5.5 Model registry with promotion states
Auto-rollback from LightGBM to Random Forest is not enough — we also need a way to run a new candidate in **shadow** for evaluation without serving it. The `active | shadow | retired` state machine gives us champion-challenger, demotion, and historical traceability in one table.

### 5.6 Feedback learning is **advisory**, not automatic
The weight tuner writes proposals to a JSON file. An operator reviews them before promoting into config. This prevents weight oscillation during the first few weeks of thin feedback data. Once feedback volume is stable, we can make the tuner auto-promote behind a flag.

### 5.7 Non-PO expenses have their own capture path
Operational expenses (legal fees, consultancy, ad-hoc travel, ad spends) never go through a PO and arrive in the ERP too late. A dedicated table + API + Streamlit form capture them at commitment time so S6 sees them before they hit cash.

### 5.8 Reconciliation closes the loop
A forecast without an actual-vs-predicted check is untethered. The reconciliation job joins every `ForecastOutput` with its corresponding `ActualOutcome` (pushed from Data Hub or entered manually) and produces the composite cash-accuracy KPI. That KPI is the metric the client grades us on — `0.7 · cash_accuracy + 0.3 · days_accuracy` — and it's exposed to Prometheus for the monitoring board.

---

## 6. How This Answers Each Client Requirement

Mapping each Q&A item to the implementation.

| Q&A ask | How we address it |
|---------|-------------------|
| Q1 Thin-data handling | Hierarchical prior + `thin_data_threshold` config + `model_selector` + shared thin-data analyser |
| Q2 Non-PO expense capture | Dedicated DB table, FastAPI router, Streamlit form — emits `bill.created` on submit |
| Q3 Feature store at 1.5k-3k rows | SQLAlchemy-backed feature registry; SQLite ships today, Postgres ready via config |
| Q4 Feature versioning + in-flight policy | Version state machine (draft → active → frozen → retired); reads resolve to active version automatically |
| Q5 Data Hub event-push ingestion | HMAC-signed webhook + bulk + idempotency + DLQ |
| Q6 Volume-based retraining | Event-counter-driven partial DAG runs (`orchestrator/volume_trigger.py`) |
| Q7 Cash accuracy > days accuracy | Composite KPI with configurable weights (default 0.7 / 0.3) |
| Q8 Cold-start + per-customer variance (**core unlock**) | Hierarchical prior with empirical-Bayes shrinkage |
| Q9 LightGBM → RF auto-rollback | Model selector + model registry with promotion states |
| Q10 Actual-vs-forecast reconciliation | `actual_outcomes` table + reconciliation job + summary JSON |
| Q11 RE weights from scratch | Weight tuner writes NNLS-based proposals; operator promotes |
| Q12 Multi-entity (not MVP) | `tenant_id` on every table + `tenant_context` context-var + scoped registries |
| Q13 Open source + in-cloud | Every dependency OSS; self-hosted Docker/K8s manifests |
| Q14 Consume from Data Hub | Inbound + outbound adapters; ERP is never contacted directly |

---

## 7. Data Flow at a Glance

```
 Data Hub (external) ──push──►  ingestion/adapter
                                     │ idempotent + DLQ on failure
                                     ▼
                              Event Bus  (persisted)
                                     │
                    ┌────────────────┼────────────────┐
                    ▼                ▼                ▼
           volume_trigger     default listeners   custom subscribers
                    │                │
                    └─► Scheduler.run_subgraph(keys)

 Master pipeline:
   feature_table ─► S1, S2, Credit Risk (ML + prior + selector)
                 ─► S3, S4, S5, S6 (rule-based)
                 ─► S7 (normalise → trust → dedup → audit)
                 ─► Recommendation Engine

 Human feedback:
   recommendation → user accept/reject → feedback_store
   (later) realised cash from Data Hub → reconciliation → KPI
                                                       │
                                                       └► weight_tuner proposal

 Outputs:
   forecast_outputs (DB) ─► API + Streamlit
   run_audit             ─► monitoring
   forecast.published    ─► outbound publisher ─► Data Hub
```

---

## 8. What's Deliberately Out of Scope

We were deliberate about **not** building these yet:

- **Survival / hazard models for payment timing** — Phase 2+ per the SDD.
- **Monte Carlo simulation for cash bands** — Phase 2+.
- **Reinforcement learning for recommendation ranking** — Phase 3+.
- **Direct ERP/CRM connectors** — the Data Hub owns that path; we consume from it.
- **Auto-promotion of tuned RE weights** — advisory only until feedback volume stabilises.
- **Kafka / SNS / SQS** — event bus is in-process + DB-persisted; broker swap is a single adapter when needed.
- **Alembic-managed Postgres migrations** — plain SQLAlchemy `create_all` + ALTER-on-upgrade is enough until the schema stops changing.

Every one of these has a clean insertion point in the current code. None require a re-architecture to add.

---

## 9. Current State — What's Verified

| Verification | Result |
|--------------|--------|
| Migrations 001 → 002 → 003 | Run clean |
| Full DAG run (feature_table → S7 → RE) | All 10 tasks SUCCESS |
| Event-driven partial re-run | `invoice.created` → S1 subgraph fires, `event_log.processed=1` |
| Multi-tenant scoping | `tenant=default` stamped on every event + audit row |
| Unit + integration test suite | 23 / 23 pass |
| Smoke test of 10 v2.1 additions | 10 / 10 pass (ingestion idempotency, DLQ, non-PO, model registry, RE feedback, reconciliation, cash KPI, outbound publisher, feature version policy, volume trigger) |

---

## 10. Summary

The platform is **deterministic where the business rules are clear**, **ML-augmented where behaviour varies**, and **prior-backed where data is thin**. It's **event-reactive** because treasury reality moves event-by-event. It's **tenant-scoped and audited** because the client runs multiple entities and cares about lineage. Every line of code has a reason to exist and a section of the SDD or Q&A it answers.

Full usage docs: [README_v2.md](README_v2.md)
File-level flow diagrams: [README_FLOWS.md](README_FLOWS.md)
