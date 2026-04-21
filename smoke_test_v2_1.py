"""
Smoke test for v2.1 additions
=============================
Direct Python calls (no HTTP server) to verify every untested piece
works end-to-end. Each test is isolated; failures don't cascade.

Run:
    python smoke_test_v2_1.py
"""

import json
import os
import sys
import traceback
from datetime import datetime, timedelta

# Keep outbound publisher offline so we exercise the JSONL fallback path
os.environ.pop("DATA_HUB_URL", None)

# ANSI colour
OK = "\033[92m[ OK ]\033[0m"
FAIL = "\033[91m[FAIL]\033[0m"
INFO = "\033[94m[INFO]\033[0m"

results = []

def run(label, fn):
    print(f"\n--- {label} ---")
    try:
        fn()
        print(OK, label)
        results.append((label, True, None))
    except Exception as e:
        print(FAIL, label, "->", e)
        traceback.print_exc()
        results.append((label, False, str(e)))


# ==============================================================
# A. Data Hub ingestion (happy path)
# ==============================================================
def test_a_data_hub_ingest():
    from ingestion import ingest_event
    envelope = {
        "envelope_id": f"smoke-{datetime.utcnow().timestamp()}",
        "type": "invoice.updated",
        "tenant_id": "default",
        "occurred_at": datetime.utcnow().isoformat() + "Z",
        "data": {"invoice_id": "SMOKE-INV-1", "amount": 99000},
    }
    result = ingest_event(envelope)
    print(INFO, "ingest_event result:", result)
    assert result["status"] in ("queued", "duplicate"), result

    # Idempotency: second call should be 'duplicate'
    again = ingest_event(envelope)
    print(INFO, "second call (idempotency):", again)
    assert again["status"] == "duplicate", again


# ==============================================================
# B. Data Hub DLQ (malformed envelope)
# ==============================================================
def test_b_dlq():
    from ingestion import ingest_event
    from db.connection import get_session
    from db.models import IngestionDLQ

    bad = {"type": "invoice.created"}   # missing tenant_id + data
    result = ingest_event(bad)
    print(INFO, "malformed ingest result:", result)
    assert result["status"] == "dlq", result

    with get_session() as s:
        row = s.query(IngestionDLQ).order_by(IngestionDLQ.id.desc()).first()
    print(INFO, f"DLQ row: id={row.id} reason={row.reason}")
    assert row.reason == "malformed"


# ==============================================================
# C. Non-PO expense (DB layer only; HTTP layer tested separately)
# ==============================================================
def test_c_non_po_expense():
    from db.connection import get_session
    from db.models import NonPOExpense

    expense = NonPOExpense(
        tenant_id="default",
        submitted_by="smoke",
        category="Legal",
        description="smoke-test legal retainer",
        amount=150_000,
        currency="INR",
        expected_date=datetime.utcnow() + timedelta(days=15),
        confidence=0.9,
        recurrence="none",
    )
    with get_session() as s:
        s.add(expense)
        s.commit()
        eid = expense.id
    print(INFO, f"inserted NonPOExpense id={eid}")
    assert eid is not None


# ==============================================================
# D. Model registry (promote + read active variant)
# ==============================================================
def test_d_model_registry():
    from steps.shared.model_registry import promote, demote, active_variants, history

    promote("s1_ar_prediction", "primary", "v-smoke-1",
            metric_name="test_mae", metric_value=6.5,
            reason="smoke test")
    active = active_variants("s1_ar_prediction")
    print(INFO, "active variants:", active)
    assert any(a["variant"] == "primary" and a["version"] == "v-smoke-1" for a in active)

    promote("s1_ar_prediction", "primary", "v-smoke-2",
            metric_name="test_mae", metric_value=6.0)
    hist = history("s1_ar_prediction")
    print(INFO, f"history rows: {len(hist)}")
    assert any(h["version"] == "v-smoke-1" and h["state"] == "retired" for h in hist)
    assert any(h["version"] == "v-smoke-2" and h["state"] == "active" for h in hist)


# ==============================================================
# E. Recommendation feedback + weight tuner
# ==============================================================
def test_e_recommendation_feedback():
    from steps.recommendation_engine.feedback_store import (
        record, attach_realised_impact, load_training_frame,
    )
    from steps.recommendation_engine.weight_tuner import propose

    rec_id = f"SMOKE-REC-{datetime.utcnow().timestamp()}"
    fid = record(
        recommendation_id=rec_id,
        lever="collections",
        action="accepted",
        predicted_cash_impact=50_000,
        actor="smoke",
        payload={"score_components": {
            "cash_improvement": 0.9, "risk_reduction": 0.2,
            "target_alignment": 0.5, "feasibility": 0.8,
        }},
    )
    print(INFO, f"recorded feedback id={fid}")
    ok = attach_realised_impact(rec_id, 45_000)
    assert ok
    frame = load_training_frame()
    print(INFO, f"training frame rows: {len(frame)}")
    assert any(r["payload"].get("score_components") for r in frame if r.get("payload"))

    proposal = propose(
        current_weights={"cash_improvement": 0.4, "risk_reduction": 0.3,
                         "target_alignment": 0.2, "feasibility": 0.1},
        min_samples=1,  # lower bar so smoke test can fit
    )
    print(INFO, "weight_tuner status:", proposal["status"])
    assert proposal["status"] in ("proposed", "skipped", "degenerate")


# ==============================================================
# F. Reconciliation (insert actual + run reconcile)
# ==============================================================
def test_f_reconciliation():
    from db.connection import get_session
    from db.models import ForecastOutput
    from reconciliation import reconcile, record_actual

    # Seed a forecast row and a matching actual, so reconcile has something to join
    ref_id = f"SMOKE-REF-{datetime.utcnow().timestamp()}"
    forecast_date = datetime.utcnow() + timedelta(days=10)
    with get_session() as s:
        s.add(ForecastOutput(
            tenant_id="default",
            run_id="smoke-run",
            source_model="s1_ar_prediction",
            entity_id="C-smoke",
            reference_id=ref_id,
            event_date=forecast_date,
            amount=100_000.0,
            direction="inflow",
            confidence=0.8,
        ))
        s.commit()

    record_actual(
        reference_id=ref_id,
        source_type="AR",
        actual_date=forecast_date + timedelta(days=3),  # 3 days late
        actual_amount=95_000.0,                         # 5% under
    )

    summary = reconcile(run_id="smoke-run", tenant_id="default")
    print(INFO, "reconcile summary:", json.dumps(summary, indent=2, default=str))
    assert summary["matched_rows"] >= 1
    assert summary["mae_days"] is not None


# ==============================================================
# G. Cash-accuracy KPI (reads reconciliation summary written by F)
# ==============================================================
def test_g_cash_accuracy():
    from monitoring.cash_accuracy import compute
    kpi = compute(tenant_id="default", run_id="smoke-run")
    print(INFO, "cash_accuracy:", json.dumps(kpi, indent=2))
    assert kpi is not None
    assert "kpi" in kpi and 0 <= kpi["kpi"] <= 100


# ==============================================================
# H. Outbound publisher (JSONL fallback)
# ==============================================================
def test_h_outbound_publisher():
    from ingestion.outbound import publish
    from pathlib import Path
    result = publish("forecast.published", {
        "run_id": "smoke-run",
        "summary": "smoke-test forecast",
    })
    print(INFO, "publish result:", result)
    assert result["mode"] == "local"
    assert Path(result["path"]).exists()


# ==============================================================
# I. Feature version policy (register draft + promote + resolve)
# ==============================================================
def test_i_feature_version_policy():
    import pandas as pd
    from feature_store import FeatureRegistry, promote, resolve_active_version

    reg = FeatureRegistry("customer_features")
    v1 = reg.write(
        pd.DataFrame([{"customer_id": "C-smoke", "avg_days_to_pay": 20.0}]),
        entity_col="customer_id",
        version="smoke_v1",
    )
    promote("customer_features", v1)
    active = resolve_active_version("customer_features")
    print(INFO, f"active version: {active}")
    assert active == v1


# ==============================================================
# J. Volume trigger (counter increments without firing retrain)
# ==============================================================
def test_j_volume_trigger():
    from events.event_bus import bus
    from events.triggers import EventName
    from orchestrator.volume_trigger import peek_counters, register_volume_listeners
    import orchestrator.volume_trigger as vt_mod

    # Patch Scheduler.run_subgraph so we don't actually retrain during smoke
    original = vt_mod.Scheduler.run_subgraph
    calls = []
    vt_mod.Scheduler.run_subgraph = staticmethod(
        lambda keys: calls.append(list(keys)) or {}
    )
    try:
        # Lower the threshold so we hit it with a handful of events
        vt_mod._trigger._thresholds["s1_ar_prediction"] = 3
        register_volume_listeners()
        for _ in range(3):
            bus.emit(EventName.INVOICE_CREATED, {"invoice_id": "smoke"})
        print(INFO, "counters after 3 emits:", peek_counters())
        print(INFO, "run_subgraph calls captured:", calls)
        assert any("s1_ar_prediction" in c for c in calls)
    finally:
        vt_mod.Scheduler.run_subgraph = staticmethod(original)


# ==============================================================
# Runner
# ==============================================================
if __name__ == "__main__":
    # Ensure smoke runs against 'default' tenant (has existing data)
    os.environ.setdefault("CASHFLOW_TENANT_ID", "default")

    tests = [
        ("A. Data Hub ingestion",      test_a_data_hub_ingest),
        ("B. Data Hub DLQ",             test_b_dlq),
        ("C. Non-PO expense (DB)",      test_c_non_po_expense),
        ("D. Model registry",           test_d_model_registry),
        ("E. RE feedback + tuner",      test_e_recommendation_feedback),
        ("F. Reconciliation",           test_f_reconciliation),
        ("G. Cash-accuracy KPI",        test_g_cash_accuracy),
        ("H. Outbound publisher",       test_h_outbound_publisher),
        ("I. Feature version policy",   test_i_feature_version_policy),
        ("J. Volume trigger",           test_j_volume_trigger),
    ]

    for label, fn in tests:
        run(label, fn)

    print("\n" + "=" * 60)
    print(" SMOKE TEST SUMMARY")
    print("=" * 60)
    passed = sum(1 for _, ok, _ in results if ok)
    failed = len(results) - passed
    for label, ok, err in results:
        mark = OK if ok else FAIL
        print(f"  {mark} {label}" + (f"  ({err})" if err else ""))
    print("=" * 60)
    print(f"  {passed} passed, {failed} failed")
    print("=" * 60)

    sys.exit(0 if failed == 0 else 1)
