# Proposed Project Structure

## Cash Flow Forecasting Platform — Production-Grade Architecture

A complete, tenant-scoped, event-reactive forecasting platform built to the **CashFlow Solution Design Document (SDD v17)** and refined against the client Q&A.

---

## At a Glance

| Metric | Count |
|--------|-------|
| **Architectural layers** | 5 |
| **Top-level folders** | 15 |
| **Python modules** | ~100 |
| **Forecasting modules (S1–S7 + RE)** | 9 |
| **Persisted DB tables** | 11 |
| **Migration scripts** | 3 |
| **API endpoint groups** | 6 |
| **Event types** | 9 |
| **Test files** | 11 + 1 smoke test |
| **Config files (YAML)** | 10 |

---

## Architecture in Five Layers

```
┌────────────────────────────────────────────────────────────────┐
│  5 · PRESENTATION                                              │
│     FastAPI + Streamlit + Prometheus endpoints                 │
│     [ app/ · app/routers/ · app/pages/ ]                       │
├────────────────────────────────────────────────────────────────┤
│  4 · DOMAIN LOGIC                                              │
│     S1–S7 forecasting modules + Recommendation Engine          │
│     Shared cold-start prior + model selector + registry        │
│     Reconciliation + Cash-accuracy KPI                         │
│     [ steps/ · reconciliation/ · monitoring/cash_accuracy.py ] │
├────────────────────────────────────────────────────────────────┤
│  3 · ORCHESTRATION                                             │
│     DAG runner · Event bus · Volume-triggered retraining       │
│     [ orchestrator/ · events/ · pipeline/ (legacy) ]           │
├────────────────────────────────────────────────────────────────┤
│  2 · INTEGRATION                                               │
│     Data Hub inbound + outbound · DLQ · Idempotency            │
│     [ ingestion/ ]                                             │
├────────────────────────────────────────────────────────────────┤
│  1 · INFRASTRUCTURE                                            │
│     Database · Feature store · Audit · Security · Monitoring   │
│     [ db/ · feature_store/ · audit/ · core/ · security/        │
│       · monitoring/ ]                                          │
└────────────────────────────────────────────────────────────────┘
```

**Design rule:** lower layers have no knowledge of higher ones. Higher layers never bypass lower ones.

---


## Module Inventory · 9 Forecasting Modules

| Code | Name | Type | Primary output |
|------|------|------|----------------|
| **S1** | AR Collections Prediction | ML (LightGBM + RF) | Expected days-to-pay per invoice |
| **S2** | AP Payment Prediction + Treasury | ML + rule | Payment timing + liquidity gate decisions |
| **Credit Risk** | Risk Classification | ML (multiclass) | LOW / MEDIUM / HIGH per customer |
| **S3** | WIP Billing Forecast | Rule-based | Expected cash from project milestones |
| **S4** | Sales Pipeline Forecast | Rule-based | Expected cash from CRM deals |
| **S5** | Contingent Inflows | Deterministic | Loans, grants, refunds, insurance |
| **S6** | Expense Forecast | Category-based | Salary, tax, rent, PO + non-PO |
| **S7** | Cash Aggregation | Unification | Unified daily cash position |
| **RE** | Recommendation Engine | Scoring + ranking | Ranked actionable recommendations |

**Shared services:** cold-start prior · model selector · model registry · thin-data analyser — reused across every ML module.

---

## Data Model · 11 Tenant-Scoped Tables

| # | Table | Role | Introduced |
|---|-------|------|------------|
| 1 | `feature_snapshots` | Versioned feature store | v2 |
| 2 | `forecast_outputs` | S1–S7 + RE cash events | v2 |
| 3 | `run_audit` | One row per DAG run | v2 |
| 4 | `event_log` | Every emitted event (replayable) | v2 |
| 5 | `non_po_expenses` | Manually-captured expenses | v2.1 |
| 6 | `actual_outcomes` | Realised cash from ERP | v2.1 |
| 7 | `feature_versions` | State machine draft→active→frozen | v2.1 |
| 8 | `recommendation_feedback` | User accept/reject + realised impact | v2.1 |
| 9 | `model_registry` | Promotion state per (tenant, model, variant) | v2.1 |
| 10 | `ingestion_dlq` | Dead letter queue | v2.1 |
| 11 | `ingestion_seen` | envelope_id idempotency ledger | v2.1 |

Every row carries `tenant_id`. Zero data-leak risk between tenants at the query layer.

---

## Event Catalogue · 9 Event Types

| Event | Default listener |
|-------|------------------|
| `invoice.created / .paid / .updated` | S1 subgraph |
| `bill.created / .paid / .updated` | S2 subgraph |
| `customer.updated / vendor.updated` | feature_table rebuild (cascades) |
| `forecast.published` | Outbound publisher → Data Hub |
| `feature_store.refreshed` | Reserved for future |

All events persist to `event_log` before dispatch. Failed handlers leave rows with `processed=0` for replay.

---

## Config Surface · All YAML

| File | Drives |
|------|--------|
| `config.yml` | DB · tenancy · MLflow · KPI weights · retraining thresholds |
| `config/s1_ar_prediction.yml` | Features · hyperparams · split · cold_start · model_selector |
| `config/s2_ap_prediction.yml` | Same + liquidity_gate + treasury |
| `config/credit_risk.yml` | Classification + class imbalance |
| `config/s3_wip_forecast.yml` | Milestone rules + lag |
| `config/s4_pipeline_forecast.yml` | Stage probabilities + cohorts |
| `config/s5_contingent_inflows.yml` | Confidence by approval status |
| `config/s6_expense_forecast.yml` | Confidence by category |
| `config/s7_cash_aggregation.yml` | Source trust + dedup window |
| `config/recommendation_engine.yml` | Scoring weights + lever caps + constraints |

**Rule:** if it's tunable, it lives in a YAML. Behaviour changes are config edits, not code edits.

---

## Key Additions from Client Q&A (v2.1)

Every one of the 14 items from `Vaibhav Q&A.xlsx` has a home in the structure:

| Client ask | Where it lives |
|------------|----------------|
| Multi-entity (2-3 tenants) | `security/tenant_context.py` + `tenant_id` on every table |
| Cold-start + per-customer variance ⭐ | `steps/shared/cold_start.py` — hierarchical prior |
| LightGBM → RF auto-rollback | `steps/shared/model_selector.py` + `model_registry.py` |
| Non-PO expense UI | `app/routers/non_po_expenses.py` + `app/pages/non_po_expense_form.py` |
| Data Hub event-push + HMAC | `ingestion/data_hub_adapter.py` + `idempotency.py` |
| Forecast ↔ Actual reconciliation | `reconciliation/reconcile.py` + `actual_outcomes` table |
| Cash-accuracy > days-accuracy KPI | `monitoring/cash_accuracy.py` (0.7/0.3 composite) |
| Volume-triggered retraining | `orchestrator/volume_trigger.py` |
| Feature versioning + in-flight policy | `feature_store/version_policy.py` state machine |
| RE weights from scratch → learning | `steps/recommendation_engine/weight_tuner.py` |
| Thin-data handling (S1 + S2) | `steps/shared/thin_data.py` + config `thin_data_threshold` |
| Outbound publishing to Data Hub | `ingestion/outbound.py` |
| Open-source + in-cloud | Every dep OSS · self-hosted Docker/K8s |
| Consume from Data Hub not ERP | `ingestion/` is the only upstream entry point |

⭐ **Core architectural unlock** — the three-level hierarchical prior that handles cold-start and per-customer variance.

---

## Design Principles · Six Rules

1. **Deterministic first, ML additive.** Rule-based modules produce the baseline; ML adjusts it.
2. **Feature store is the only source of truth.** No module re-derives features from raw data.
3. **Events, not cron.** Batch runs layer on top of events, not the other way around.
4. **Everything tenant-scoped.** `tenant_id` on every row, `tenant_context` for every call.
5. **Audit + lineage non-negotiable.** Every run, every dataset, every event is traceable.
6. **Config-driven.** If it's tunable, it lives in YAML.

---

## What's Verified to Work End-to-End

| Check | Result |
|-------|--------|
| All 3 DB migrations | ✓ Clean |
| Full DAG run (feature_table → S7 → RE) | ✓ 10 tasks SUCCESS |
| Event-driven partial re-run | ✓ `invoice.created` fires S1 subgraph |
| Multi-tenant scoping | ✓ `tenant_id` stamped throughout |
| Unit + integration tests | ✓ 23 / 23 pass |
| v2.1 smoke tests (10 areas) | ✓ 10 / 10 pass |

---

## What's Deliberately Out of Scope

Every deferred item has a clean insertion point in the current structure:

- Survival / hazard models for payment timing (Phase 2+)
- Monte Carlo simulation for cash bands (Phase 2+)
- Reinforcement learning for recommendation ranking (Phase 3+)
- Direct ERP/CRM connectors — Data Hub owns this path
- Auto-promotion of tuned RE weights — advisory only until volume stabilises
- Kafka / SNS / SQS — in-process event bus is persistence-backed; broker swap is one adapter
- Alembic — plain SQLAlchemy migrations suffice until schema stops changing

None require a re-architecture to add later.

---

## Where to Start Reading

| Audience | Document |
|----------|----------|
| Client / stakeholder | [README_APPROACH.md](README_APPROACH.md) — design rationale |
| New engineer | [README_FLOWS.md](README_FLOWS.md) — Mermaid flows + 3 SDD scenarios |
| Deploying / running | [README_v2.md](README_v2.md) — usage + API reference |
| Any individual folder | `<folder>/README.md` — file-level docs in every module |

---

## Summary

One codebase. Five layers. Nine forecasting modules. Eleven tenant-scoped tables. Every open question from the client Q&A answered with a named file. Every design decision has a "why" documented next to the code.

**Not an MVP — built for multi-entity production from day one.**
