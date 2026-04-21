import json

from audit.audit_logger import AuditLogger
from audit.lineage_tracker import LineageTracker


def test_audit_record_roundtrip(tmp_audit_paths):
    log = AuditLogger()
    log.record("run_start", actor="tester", run_id="r1", pipeline="full")
    log.record("run_finish", actor="tester", run_id="r1", status="success")
    tail = log.tail(10)
    assert [e["action"] for e in tail] == ["run_start", "run_finish"]
    assert tail[0]["run_id"] == "r1"


def test_lineage_trace_walks_backwards(tmp_audit_paths):
    lt = LineageTracker()
    lt.record("customer_features", inputs=["raw.customers", "raw.invoices"],
              producer="feature_table", run_id="r1")
    lt.record("s1_predictions", inputs=["customer_features"],
              producer="s1_ar_prediction", run_id="r1")
    lt.record("cash_forecast", inputs=["s1_predictions"],
              producer="s7_cash_aggregation", run_id="r1")

    trail = lt.trace("cash_forecast", depth=5)
    producers = [r["producer"] for r in trail]
    assert "s7_cash_aggregation" in producers
    assert "s1_ar_prediction" in producers
    assert "feature_table" in producers
