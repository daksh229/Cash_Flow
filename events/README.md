# events/

In-process publish/subscribe bus with DB persistence. Every emit is written to `event_log` (tenant-scoped) before dispatch, so replays and audit are possible.

## Files

| File | Purpose |
|------|---------|
| `event_bus.py` | `EventBus` class + `bus` singleton. `bus.subscribe(event_name, handler)`, `bus.emit(name, payload)`, `bus.replay_pending(event_name?)`. Failed handlers leave the row with `processed=0` for later replay. |
| `triggers.py` | `EventName` catalogue — single place listing every event the system knows about. Grep-friendly constants (`INVOICE_CREATED`, `BILL_PAID`, ...). |
| `listeners.py` | Default subscription wiring. `register_default_listeners()` maps invoice events → S1 subgraph, bill events → S2, customer/vendor updates → feature rebuild. |
| `__init__.py` | Re-exports `EventBus`, `bus`, `EventName`. |

## Run individually

Quick emit + check:

```python
from events.event_bus import bus
from events.triggers import EventName
from events.listeners import register_default_listeners

register_default_listeners()
bus.emit(EventName.INVOICE_CREATED, {"invoice_id": "INV-1"})
```

Replay anything that failed previously:

```python
from events.event_bus import bus
bus.replay_pending()   # or bus.replay_pending(event_name="bill.paid")
```

## Role in orchestration pipeline

- [ingestion/data_hub_adapter.py](../ingestion/data_hub_adapter.py) emits events after mapping Data Hub envelopes.
- [app/routers/non_po_expenses.py](../app/routers/non_po_expenses.py) emits `bill.created` when a user submits a non-PO expense.
- Listeners in `listeners.py` translate events → `Scheduler.run_subgraph([...])` calls (see [orchestrator/](../orchestrator/)).
- [orchestrator/volume_trigger.py](../orchestrator/volume_trigger.py) subscribes to the same events to count new rows per model.

## Add a new event

1. Add the constant to `triggers.py`:
   ```python
   FORECAST_PUBLISHED = "forecast.published"
   ```
2. Add a listener in `listeners.py`:
   ```python
   def _on_published(payload):
       ...
   bus.subscribe(EventName.FORECAST_PUBLISHED, _on_published)
   ```
3. Emit anywhere:
   ```python
   bus.emit(EventName.FORECAST_PUBLISHED, {"run_id": "..."})
   ```

## Related

- Storage: `event_log` table in [db/models.py](../db/models.py).
- Consumers: [orchestrator/scheduler.py](../orchestrator/scheduler.py), [orchestrator/volume_trigger.py](../orchestrator/volume_trigger.py), [ingestion/outbound.py](../ingestion/outbound.py).
- Unit tests: [tests/unit/test_event_bus.py](../tests/unit/test_event_bus.py), [tests/integration/test_event_to_subgraph.py](../tests/integration/test_event_to_subgraph.py).
