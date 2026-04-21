"""
Event Bus
=========
In-process pub/sub with DB-backed persistence for replayability.
Listeners register against an event name; publishers call `bus.emit(...)`.

Each emitted event is written to event_log (processed=0), then dispatched
to listeners. On successful dispatch the row is marked processed=1.
If a listener raises, the event stays pending and can be replayed later
by `bus.replay_pending()`.
"""

import logging
from collections import defaultdict
from typing import Callable, Dict, List

from db.connection import get_session
from db.models import EventLog
from security.tenant_context import current_tenant

logger = logging.getLogger(__name__)


class EventBus:
    def __init__(self):
        self._subscribers: Dict[str, List[Callable]] = defaultdict(list)

    def subscribe(self, event_name: str, handler: Callable):
        self._subscribers[event_name].append(handler)
        logger.debug("Subscribed %s -> %s", handler.__name__, event_name)

    def emit(self, event_name: str, payload: dict = None):
        payload = payload or {}
        with get_session() as s:
            row = EventLog(
                tenant_id=current_tenant(),
                event_name=event_name,
                payload=payload,
                processed=0,
            )
            s.add(row)
            s.commit()
            event_id = row.id

        handlers = list(self._subscribers.get(event_name, []))
        logger.info("Event '%s' emitted (id=%s, %d handlers)",
                    event_name, event_id, len(handlers))

        failed = False
        for h in handlers:
            try:
                h(payload)
            except Exception as e:
                failed = True
                logger.error("Handler %s for '%s' failed: %s",
                             h.__name__, event_name, e, exc_info=True)

        if not failed:
            with get_session() as s:
                row = s.query(EventLog).get(event_id)
                if row:
                    row.processed = 1
                    s.commit()

    def replay_pending(self, event_name: str = None):
        with get_session() as s:
            q = s.query(EventLog).filter(EventLog.processed == 0)
            if event_name:
                q = q.filter(EventLog.event_name == event_name)
            pending = q.order_by(EventLog.id).all()
            for row in pending:
                logger.info("Replaying event id=%s name=%s", row.id, row.event_name)
                for h in self._subscribers.get(row.event_name, []):
                    try:
                        h(row.payload or {})
                    except Exception as e:
                        logger.error("Replay failed for %s: %s", h.__name__, e)
                        break
                else:
                    row.processed = 1
            s.commit()


bus = EventBus()
