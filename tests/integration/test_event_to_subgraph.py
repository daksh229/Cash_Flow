"""
Integration test: invoice.* events trigger the S1 subgraph via listeners.
We monkey-patch Scheduler.run_subgraph so the test stays fast and does
not depend on trained ML artifacts.
"""

from events.event_bus import bus
from events.triggers import EventName
from events import listeners


def test_invoice_created_calls_subgraph_with_s1(tmp_db, reset_event_bus, monkeypatch):
    captured = []

    def fake_run_subgraph(keys):
        captured.append(list(keys))
        return {}

    monkeypatch.setattr(
        "events.listeners.Scheduler.run_subgraph", staticmethod(fake_run_subgraph)
    )
    listeners.register_default_listeners()
    bus.emit(EventName.INVOICE_CREATED, {"invoice_id": "INV-1"})
    assert captured == [["s1_ar_prediction"]]


def test_bill_paid_calls_subgraph_with_s2(tmp_db, reset_event_bus, monkeypatch):
    captured = []
    monkeypatch.setattr(
        "events.listeners.Scheduler.run_subgraph",
        staticmethod(lambda keys: captured.append(list(keys)) or {}),
    )
    listeners.register_default_listeners()
    bus.emit(EventName.BILL_PAID, {"bill_id": "B-9"})
    assert captured == [["s2_ap_prediction"]]


def test_customer_updated_triggers_feature_rebuild(tmp_db, reset_event_bus, monkeypatch):
    captured = []
    monkeypatch.setattr(
        "events.listeners.Scheduler.run_subgraph",
        staticmethod(lambda keys: captured.append(list(keys)) or {}),
    )
    listeners.register_default_listeners()
    bus.emit(EventName.CUSTOMER_UPDATED, {"customer_id": "C-1"})
    assert captured == [["feature_table"]]
