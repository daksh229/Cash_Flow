from events.event_bus import EventBus, bus
from events.triggers import EventName


def test_subscribe_and_emit(tmp_db, reset_event_bus):
    received = []
    reset_event_bus.subscribe("x.happened", lambda p: received.append(p))
    reset_event_bus.emit("x.happened", {"id": 1})
    assert received == [{"id": 1}]


def test_event_is_persisted_and_marked_processed(tmp_db, reset_event_bus):
    from db.connection import get_session
    from db.models import EventLog

    reset_event_bus.subscribe("x.happened", lambda p: None)
    reset_event_bus.emit("x.happened", {"id": 2})
    with get_session() as s:
        rows = s.query(EventLog).all()
    assert len(rows) == 1 and rows[0].processed == 1


def test_failing_handler_leaves_event_pending(tmp_db, reset_event_bus):
    from db.connection import get_session
    from db.models import EventLog

    def bad(_): raise RuntimeError("boom")
    reset_event_bus.subscribe("x.broken", bad)
    reset_event_bus.emit("x.broken", {})
    with get_session() as s:
        row = s.query(EventLog).one()
    assert row.processed == 0


def test_event_name_catalogue_enumerates_all():
    names = EventName.all()
    assert "invoice.created" in names
    assert "bill.paid" in names
    assert len(names) == len(set(names))
