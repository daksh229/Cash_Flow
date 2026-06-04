# Project Plan — Cash Flow Forecasting Platform

## Real-Data Rollout · 20-Week Sprint Schedule

This plan covers the transition from the v2.1 synthetic-data baseline (current state) to a multi-tenant production rollout on real Data Hub feeds. It is structured around eight sprints, with extra buffer in three high-risk phases (DH integration, recommendation engine, go-live).

Companion documents:
- [PROJECT_STRUCTURE.md](PROJECT_STRUCTURE.md) — current code structure
- [README_APPROACH.md](README_APPROACH.md) — design rationale
- [README_FLOWS.md](README_FLOWS.md) — file-level flow diagrams
- [README_v2.md](README_v2.md) — usage + API reference

---

## 1. Executive Summary

| | |
|---|---|
| **Total duration** | **20 weeks · 5 months** |
| **Sprints** | 8 (mostly 2-week, with 3-week buffers in Sprint 1 and 7, and a 4-week Sprint 6) |
| **Team** | 2 engineers + 1 PM (+ ad-hoc data-science input) |
| **Tenants at launch** | 2-3 entities |
| **Go-live date** | End of Week 18 |
| **Handover** | End of Week 20 |
| **Budget posture** | Fixed scope · 4 weeks of buffer built in |

**Critical-path dependencies (client-side):**
1. Data Hub schema + signing key by Week 1 (Sprint 1).
2. Treasury users available for UAT by Week 12 (Sprint 6B).
3. Production cloud + DB infra ready by Week 16 (Sprint 7).

---

## 2. Assumptions

| Assumption | Value |
|------------|-------|
| Sprint length | 2 weeks default · 3-4 weeks where flagged |
| Engineering team | 2 engineers (full-time) |
| Project management | 1 PM (50% allocation) |
| Data-science consultant | Ad-hoc, ~2 days per sprint |
| Data Hub readiness | Endpoint + first backfill by end of Sprint 1 |
| Tenant count at launch | 2-3 entities |
| UAT users | 2-3 treasury users available 4-5 sessions during Sprint 6B |
| Cloud target | Client's existing cloud (AWS / GCP / Azure — TBD) |
| Database | Postgres 16+ in production (SQLite for dev) |
| MLflow | Self-hosted in client cloud |
| Working hours | Client-team standard (will adjust ceremony times accordingly) |

---

## 3. Estimation Summary

| Phase | Sprint(s) | Weeks | Cumulative |
|-------|-----------|-------|------------|
| 1 · Data Hub integration | Sprint 1 | 3 | Week 3 |
| 2 · Real-data preprocessing | Sprint 2 | 2 | Week 5 |
| 3 · ML retraining | Sprint 3 | 2 | Week 7 |
| 4 · Rule-based + S7 calibration | Sprint 4 | 2 | Week 9 |
| 5 · Reconciliation + KPI | Sprint 5 | 2 | Week 11 |
| 6 · Recommendation Engine focus | Sprint 6 (6A + 6B) | 4 | Week 15 |
| 7 · Hardening + go-live | Sprint 7 | 3 | Week 18 |
| 8 · Hypercare | Sprint 8 | 2 | Week 20 |
| **Total** | **8 sprints** | **20** | — |

---

## 4. Visual Timeline

```
Wk:  1  2  3 │ 4  5 │ 6  7 │ 8  9 │10 11 │12 13 14 15 │16 17 18 │19 20
     ┌──S1──┐ ┌─S2─┐ ┌─S3─┐ ┌─S4─┐ ┌─S5─┐ ┌─────S6─────┐ ┌──S7──┐ ┌─S8─┐
     │ DH   │ │Pre-│ │ML  │ │Rule│ │KPI │ │   RE +     │ │Hard- │ │Hyp-│
     │ lock │ │proc│ │re- │ │+ S7│ │Recn│ │   UAT      │ │ ened │ │care│
     │      │ │    │ │trn │ │    │ │    │ │ (6A │ 6B)  │ │+ Live│ │    │
     └──────┘ └────┘ └────┘ └────┘ └────┘ └────────────┘ └──────┘ └────┘
        M1     M2*   M2     M3     M4     M5A   M5B        M6      M7
```
*M2 demo at end of S3, formal sign-off after S4*

---

## 5. Milestones

Client-visible deliverables. Each milestone has a demo and a written sign-off.

| ID | Milestone | Sprint | End of week | Sign-off artefact |
|----|-----------|--------|-------------|-------------------|
| **M1** | Integration proven | S1 | 3 | Live event flowing through DH webhook → event_log → DAG |
| **M2** | Forecast on real data | S3 | 7 | Trained models + sample predictions per tenant |
| **M3** | Unified cash position live | S4 | 9 | Daily/weekly/monthly dashboard on real data |
| **M4** | Cash-accuracy KPI published | S5 | 11 | First reconciliation summary + composite KPI per tenant |
| **M5A** | RE calibrated on real data | S6A | 13 | Stress-tested recommendations + scenario library |
| **M5B** | UAT sign-off | S6B | 15 | Treasury users approve recommendation quality |
| **M6** | Production go-live | S7 | 18 | Live system with real users on production URL |
| **M7** | Handover complete | S8 | 20 | Client ops team owns operations + close-out report |

---

## 6. Sprint Backlogs

Every sprint is structured as **goal → backlog → acceptance criteria → demo → risks**.

---

### Sprint 1 — Data Hub Integration Lock-down · 3 weeks (Week 1-3) ⬆ +1

**Goal:** Real Data Hub envelopes flowing through `/ingest/event` end-to-end with idempotency, DLQ, and successful first backfill.

**Why 3 weeks:** Foundational sprint. Schema-finalisation conversations with the DH team typically slip; an extra week prevents knock-on delay across all downstream sprints.

**Backlog:**

| ID | Task | Effort |
|----|------|--------|
| 1.1 | Finalise DH envelope schema (field names, tenant_id semantics, envelope_id source) | M |
| 1.2 | Exchange `DATA_HUB_SIGNING_KEY` + agree on retry policy (timeouts, backoff) | S |
| 1.3 | Implement adapter changes for any agreed schema deltas | M |
| 1.4 | First real backfill: bulk JSONL of last 12 months of historical events | M |
| 1.5 | Validate idempotency on real edge cases (retries, out-of-order delivery, partial duplicates) | M |
| 1.6 | Validate DLQ behaviour: malformed envelopes, unmapped event types, handler failures | S |
| 1.7 | Data profiling report: volumes, null rates, schema drift, cardinality per tenant | M |
| 1.8 | Buffer week — absorb DH delays / late schema changes / infra access issues | — |

**Acceptance criteria:**
- DH push to `/ingest/event` returns 202 + writes `event_log` row.
- Duplicate `envelope_id` returns `status=duplicate` (no double-processing).
- Malformed envelope writes to `ingestion_dlq` (not 5xx).
- Backfill completes for at least one tenant.
- Data profiling report committed to `reports/data_profiling/`.

**Demo:** Live DH push → event_log row → S1 subgraph re-run.

**Risks:**
- DH schema slips → use buffer week; fallback to bulk JSONL while webhook stabilises.
- Backfill volume higher than expected → process in batches; add streaming consumer in S2 if needed.

---

### Sprint 2 — Real-Data Preprocessing + Feature Tables · 2 weeks (Week 4-5)

**Goal:** Feature tables built from real data match SDD expectations across all tenants.

**Backlog:**

| ID | Task | Effort |
|----|------|--------|
| 2.1 | Adjust preprocessing for null/missing values per column | M |
| 2.2 | Currency normalisation (real vendors/customers span currencies) | M |
| 2.3 | Timezone + date-format harmonisation | S |
| 2.4 | Category-encoding mappings (real risk_segment / approval_status / escalation values) | S |
| 2.5 | Edge cases: zero-amount invoices, reversed payments, credit notes | M |
| 2.6 | Tune `thin_data_threshold` based on actual invoice-count distribution | S |
| 2.7 | Validate 6 feature tables against SDD field dictionary | M |
| 2.8 | Duplicate / conflicting record merge rules | M |
| 2.9 | Per-tenant data-quality scorecard | S |

**Acceptance criteria:**
- All 6 feature tables build successfully for each tenant on real data.
- Data-quality scorecard shows < 5% null rate on critical columns (or documented exception).
- `thin_data_threshold` re-derived per tenant and committed to config.
- Schema validation passes against SDD field dictionary.

**Demo:** Real feature tables for all 3 tenants + distribution plots vs synthetic baseline.

**Risks:**
- Data quality gaps not anticipated in SDD → add columns to data-quality scorecard; flag for client review.
- Schema misalignment between ERP and DH → escalate to DH team; add transformation layer in `ingestion/schema_mapper.py`.

---

### Sprint 3 — Retrain ML Modules on Real Data · 2 weeks (Week 6-7)

**Goal:** S1, S2, Credit Risk trained on real history; cold-start prior fitted per tenant.

**Backlog:**

| ID | Task | Effort |
|----|------|--------|
| 3.1 | Retrain S1 LightGBM + RF on real AR history per tenant | M |
| 3.2 | Retrain S2 LightGBM + RF on real AP history per tenant | M |
| 3.3 | Retrain Credit Risk classifier on real customer history | M |
| 3.4 | Investigate and resolve any leakage exposed (Credit Risk F1 was 0.98 on synthetic — likely leakage) | M |
| 3.5 | Fit `GlobalPrior` per tenant on real history | M |
| 3.6 | Seed `model_registry` with real artefacts; promote "primary" variant | S |
| 3.7 | Calibrate `model_selector.degradation_threshold_pct` against observed variance | S |
| 3.8 | Update `tests/regression/baselines.yml` with real baselines | S |
| 3.9 | Validate primary→baseline auto-rollback path on a synthetic degraded model | S |

**Acceptance criteria:**
- All 3 ML modules retrained per tenant.
- No target leakage in evaluation metrics.
- `GlobalPrior` saved and `model_registry` populated for each (tenant, model).
- Baselines updated and committed.
- Rollback path verified end-to-end.

**Demo:** Trained models serving predictions per tenant; show prior fallback for a brand-new customer (no history).

**Risks:**
- Real data won't support LightGBM assumptions → fall back to RF as primary; record decision in model_registry.
- Target leakage is harder to fix than expected → may need feature redesign; can absorb in S4 if minor.

---

### Sprint 4 — Rule-Based Modules + S7 Calibration · 2 weeks (Week 8-9)

**Goal:** S3 / S4 / S5 / S6 / S7 produce coherent outputs on real data; first full DAG run end-to-end.

**Backlog:**

| ID | Task | Effort |
|----|------|--------|
| 4.1 | S3 — verify milestone rules against real project data; tune `completion_threshold` + `invoice_lag_days` | M |
| 4.2 | S4 — fit stage probabilities from actual CRM close rates (replace defaults) | M |
| 4.3 | S5 — validate confidence mapping against real approval → payment history | S |
| 4.4 | S6 — calibrate `payment_lag_days` per real category; wire `non_po_expenses` into S6 input | M |
| 4.5 | S7 — tune `dedup.date_window_days` + `amount_round` based on real overlap patterns | M |
| 4.6 | S7 trust scoring — populate `source_trust` baselines from initial metric runs | S |
| 4.7 | First full DAG run on real data per tenant | M |
| 4.8 | Validate end-to-end: feature_table → S1..S6 → S7 → RE produces sensible numbers | M |

**Acceptance criteria:**
- Each rule-based module produces non-empty, sensible output on real data.
- S7 dedup rate within reason (not collapsing distinct events, not letting duplicates through).
- Full DAG run succeeds for each tenant (`run_audit.status="success"`).
- Output cash position passes sanity check vs client's manual estimate.

**Demo:** Live dashboard showing the unified daily/weekly/monthly cash position per tenant.

**Risks:**
- Rule defaults misaligned with reality → expected; addressed within sprint.
- S7 dedup too aggressive / too loose → tune iteratively; window + amount_round are config-driven.

---

### Sprint 5 — Reconciliation + Cash-Accuracy KPI · 2 weeks (Week 10-11)

**Goal:** Feedback loop producing real KPI numbers; regression gate enabled.

**Backlog:**

| ID | Task | Effort |
|----|------|--------|
| 5.1 | Wire DH push of actual outcomes → `actual_outcomes` table | M |
| 5.2 | Run first monthly reconciliation cycle per tenant | M |
| 5.3 | Calibrate `kpi.mae_days_target` to produce meaningful variance | S |
| 5.4 | Confirm or adjust `cash_weight=0.7` / `days_weight=0.3` with client | S |
| 5.5 | Add JSON metrics output to each `evaluate.py` (regression gate prerequisite) | M |
| 5.6 | Wire regression gate in CI (`pytest tests/regression`) | S |
| 5.7 | Build Grafana dashboard on top of Prometheus `/metrics` | M |
| 5.8 | Set up alerting: KPI drift, DAG failure, DLQ growth, ingestion error rate | M |

**Acceptance criteria:**
- `actual_outcomes` populated from DH for at least one full reconciliation cycle.
- Composite KPI computed per tenant and exported to Prometheus.
- Regression gate runs in CI and either passes or has documented baseline updates.
- Grafana dashboard reachable; basic alerts firing on test events.

**Demo:** Real KPI per tenant + variance waterfall (forecast vs actual).

**Risks:**
- Actual-outcome lag longer than expected (real-world ERP lag) → stretch reconciliation cadence to 6 weeks if needed.
- KPI weights need re-negotiation → trivial config change.

---

### Sprint 6 — Recommendation Engine Focus · 4 weeks (Week 12-15) ⬆⬆ +2

**Goal:** Recommendation engine calibrated on real data, validated with treasury users, feedback loop closing.

**Why 4 weeks:** RE is centralized — every other module feeds into it, every user action flows through it, and the feedback loop is what makes the system improve over time. Treating this as a single 2-week sprint underweights its complexity.

#### Sprint 6A — RE Calibration on Real Data · 2 weeks (Week 12-13)

**Backlog:**

| ID | Task | Effort |
|----|------|--------|
| 6A.1 | RE recalibration on real S7 position + real credit risk | M |
| 6A.2 | Lever-by-lever tuning: collections acceleration | M |
| 6A.3 | Lever-by-lever tuning: vendor deferral | M |
| 6A.4 | Lever-by-lever tuning: expense deferral | M |
| 6A.5 | Constraint validation (`min_cash_balance`, Tier-1 vendor protection) | S |
| 6A.6 | Initial scoring-weight sensitivity analysis | M |
| 6A.7 | Scenario library: stress-test recs against synthetic shocks (quarter-end, large invoice slip, vendor dispute) | M |
| 6A.8 | Cross-module conflict checks (e.g. RE wants to defer a vendor S2 already paid) | M |
| 6A.9 | Internal review with engineering + DS — gate to UAT | S |

**Acceptance criteria for 6A:**
- RE produces non-empty ranked recommendations per tenant.
- Stress-test scenarios produce reasonable results (no recs that breach floor or violate Tier-1).
- Cross-module conflicts surfaced + resolved or flagged for product decision.
- Internal review approves moving to UAT.

**Demo for 6A:** Stress-test scenarios + scoring-weight sensitivity analysis.

#### Sprint 6B — UAT + Feedback Loop + Tuning · 2 weeks (Week 14-15)

**Backlog:**

| ID | Task | Effort |
|----|------|--------|
| 6B.1 | Coordinate 4-5 UAT sessions with 2-3 treasury users | M |
| 6B.2 | Capture feedback live via `/recommendations/feedback` endpoint | M |
| 6B.3 | Non-PO expense form polish based on user feedback | M |
| 6B.4 | Frontend polish: filter by tenant, export to Excel, daily/weekly toggle | M |
| 6B.5 | Run `weight_tuner` proposal — review with users (likely "skipped" first time, expected) | S |
| 6B.6 | Iterate scoring components based on feedback themes | M |
| 6B.7 | Document UAT outcomes + sign-off | S |

**Acceptance criteria for 6B:**
- All planned UAT sessions completed.
- ≥ 80% of feedback items addressed or backlogged with rationale.
- Treasury users sign off on recommendation quality (M5B).
- Weight-tuner proposal generated and reviewed (even if not promoted).

**Demo for 6B:** Treasury user walks through recs live + accept/reject + tuner proposal.

**Risks for S6:**
- UAT user availability → confirm by S4; book sessions early; have recorded-walkthrough fallback.
- Recommendations too noisy → extra calibration time built into S6A.
- Lever conflicts (S2 vs RE) → identified in S6A; if blocking, push fix to S7 buffer.

---

### Sprint 7 — Multi-Tenant + Hardening + Go-Live · 3 weeks (Week 16-18) ⬆ +1

**Goal:** Platform live in client cloud with real users.

**Why 3 weeks:** Go-live is high-stakes. Extra week absorbs pen-test findings, cut-over delays, and last-minute config changes without compressing hypercare.

**Backlog:**

| ID | Task | Effort |
|----|------|--------|
| 7.1 | Configure all 2-3 tenants in production | M |
| 7.2 | Per-tenant config overrides where needed | S |
| 7.3 | Automated tenant data-isolation test in CI | S |
| 7.4 | Security review: pen-test on `/ingest/event` + RBAC audit | L |
| 7.5 | Performance test: API load + concurrent DAG runs | M |
| 7.6 | Wire alerting: PagerDuty / email on KPI drift, DAG failure, DLQ growth | M |
| 7.7 | Runbook: DLQ replay procedure | S |
| 7.8 | Runbook: stuck feature versions (promote / freeze) | S |
| 7.9 | Runbook: model rollback (registry demote / promote) | S |
| 7.10 | Runbook: emergency stop (event bus pause, DAG abort) | S |
| 7.11 | Buffer week — absorb pen-test fixes, performance tuning, last-minute config | — |
| 7.12 | Go-live cut-over (planned for end of Week 18) | M |

**Acceptance criteria:**
- All 3 tenants configured and isolation-tested.
- Pen-test findings: critical/high resolved before go-live.
- Performance test passes against agreed SLAs (TBD with client).
- All runbooks reviewed by client ops team.
- Cut-over plan signed off; rollback procedure documented.

**Demo:** Live production URL with real users + dashboards + alerts.

**Risks:**
- Pen-test finds critical issues → buffer week absorbs; if larger, trigger contingency (delay cut-over by 1 week).
- Performance under real load worse than expected → identify bottleneck; either tune or add caching layer.
- Cut-over delay → reschedule within hypercare window.

---

### Sprint 8 — Hypercare · 2 weeks (Week 19-20)

**Goal:** Stabilise. Hand over to client ops team. No new features.

**Backlog:**

| ID | Task | Effort |
|----|------|--------|
| 8.1 | Daily client stand-ups | — |
| 8.2 | Bug fixes from real usage | M |
| 8.3 | KPI tuning based on first weeks of real data | M |
| 8.4 | Second weight-tuner proposal (if enough feedback accumulated) | S |
| 8.5 | First volume-triggered retrain observed + validated | S |
| 8.6 | Handover sessions with client ops team (3-4 sessions) | M |
| 8.7 | Close-out report: KPI baselines, lessons learned, Phase 2 roadmap | M |
| 8.8 | Final retrospective with client | S |

**Acceptance criteria:**
- Open critical/high bugs at end of S8: zero.
- Client ops team can run a full DAG run + reconciliation + DLQ replay unaided.
- Close-out report delivered and signed off.

**Demo:** Final retrospective + handover — no live demo needed; production has been live for 2 weeks.

**Risks:**
- Critical bug in last week → extend hypercare; budget for one extra week.
- Client ops team not ready → schedule additional handover sessions in week 19.

---

## 7. Risk Register

| # | Risk | Likelihood | Impact | Mitigation | Owner |
|---|------|------------|--------|------------|-------|
| R1 | Data Hub delivery slips | Medium | High | Buffer in S1; CSV bulk fallback for S2-S5 | DH team + Eng |
| R2 | Real data quality worse than SDD implies | Medium | High | S2 dedicated to this; data-quality scorecard early | Eng |
| R3 | Treasury UAT users unavailable | Medium | Medium | Confirm availability in S4; recorded-walkthrough fallback | PM |
| R4 | Cold-start prior underperforms on real data | Low-Medium | Medium | 3-level fallback (prior → baseline → primary) handles graceful degradation | Eng + DS |
| R5 | Multi-tenant config drift | Low | Medium | Automated tenant-isolation test in CI before go-live | Eng |
| R6 | Pen-test finds critical issues | Medium | High | Buffer week in S7; contingency to delay cut-over by 1 week | Eng + Sec |
| R7 | RE recommendations rejected by users in UAT | Medium | High | S6A scenario library + sensitivity analysis catches issues before UAT | Eng + DS + PM |
| R8 | Client ops team not ready for handover | Low | Medium | Handover starts in S8 day 1; additional sessions if needed | PM |
| R9 | KPI baseline disagreement (cash vs days weighting) | Low | Low | Trivial config change; revisit after first reconciliation | PM |
| R10 | Performance under real load below SLA | Medium | Medium | S7 perf test; caching layer or DB pool tuning available | Eng |

---

## 8. Resource Allocation

| Sprint | Engineer 1 | Engineer 2 | PM | DS Consultant |
|--------|------------|------------|-----|----------------|
| S1 | DH adapter + idempotency | DH backfill + profiling | Schema + key exchange + DH coordination | — |
| S2 | Preprocessing | Feature table validation | Data-quality scorecard sign-off | 1 day data review |
| S3 | S1 + S2 retraining | Credit Risk + cold-start prior | Baselines update | 2 days leakage investigation |
| S4 | S3 + S4 | S5 + S6 + S7 trust/dedup | Sanity-check meeting with client | 1 day rule calibration |
| S5 | Actuals ingestion + reconcile | KPI + Grafana + alerting | Confirm KPI weights | — |
| S6A | RE calibration + scenarios | Cross-module conflict checks | Schedule UAT | 2 days RE tuning |
| S6B | UAT facilitation + iteration | Frontend / non-PO polish | UAT lead | 1 day weight tuner review |
| S7 | Tenant config + isolation tests | Perf + alerting + runbooks | Cut-over coordination + pen-test review | — |
| S8 | Bug fixes + handover | KPI tuning + retrain validation | Close-out + handover | 1 day RE re-tune |

---

## 9. Communication Cadence

| Forum | Frequency | Audience | Purpose |
|-------|-----------|----------|---------|
| Daily stand-up | Daily | Eng team | Blockers, progress |
| Sprint review (demo) | End of each sprint | Client + team | Demo + sign-off |
| Sprint retro | End of each sprint | Eng team | Process improvement |
| Client steering | Bi-weekly (every 2nd Friday) | Client lead + PM | Risks, scope, schedule |
| Hypercare stand-up | Daily during S8 | Client ops + team | Bug triage, handover |

---

## 10. Definition of Done (per sprint)

A sprint is **done** when:

- All acceptance criteria are met.
- All committed backlog items are merged + tested (or explicitly carried over with reason).
- The sprint demo has been delivered.
- No critical/high bugs are left open.
- Documentation (folder READMEs + flow diagrams) reflects what shipped.
- Client steering has signed off on the demo.

---

## 11. What's Out of Scope (for this 20-week plan)

These items have a clean insertion point in the codebase and can be added in Phase 2:

- Survival / hazard models for payment timing
- Monte Carlo simulation for cash bands
- Reinforcement learning for recommendation ranking
- Direct ERP/CRM connectors (DH owns this path)
- Auto-promotion of tuned RE weights (advisory only at launch)
- Kafka / SNS / SQS broker (in-process bus persists; broker swap is one adapter)
- Alembic-managed migrations (plain SQLAlchemy is sufficient until schema stabilises)
- Mobile app or alerts-to-mobile

Phase 2 roadmap will be drafted in S8 close-out report.

---

## 12. Change Log Against Original Estimate

| Sprint | Original | Updated | Δ | Reason |
|--------|----------|---------|---|--------|
| S1 | 2 weeks | **3 weeks** | +1 | Buffer for Data Hub schema slip |
| S6 | 2 weeks | **4 weeks** (split 6A/6B) | +2 | RE is centralized — calibration + UAT need dedicated focus |
| S7 | 2 weeks | **3 weeks** | +1 | Buffer for pen-test fixes + cut-over |
| **Total** | **16 weeks** | **20 weeks** | **+4 weeks** | Added 1 month of buffer in 3 highest-risk phases |

---

## 13. Approval

| Role | Name | Date | Sign-off |
|------|------|------|----------|
| Client lead | | | |
| Engineering lead | | | |
| Project manager | | | |
| Data Hub lead | | | |
