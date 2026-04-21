# test.py — expanded
from events.event_bus import bus
from events.triggers import EventName
from events.listeners import register_default_listeners
from db.connection import get_session
from db.models import EventLog, RunAudit

register_default_listeners()
bus.emit(EventName.INVOICE_CREATED, {"invoice_id": "INV-123"})

with get_session() as s:
    print("\n=== Last 3 events ===")
    for e in s.query(EventLog).order_by(EventLog.id.desc()).limit(3):
        print(f"  #{e.id} {e.event_name} tenant={e.tenant_id} processed={e.processed}")

    print("\n=== Last 3 runs ===")
    for r in s.query(RunAudit).order_by(RunAudit.id.desc()).limit(3):
        print(f"  {r.run_id} pipeline={r.pipeline} status={r.status}")
