# ingestion/

Bidirectional Data Hub integration: inbound webhook + bulk + DLQ + idempotency; outbound forecast publishing.

## Files

| File | Purpose |
|------|---------|
| `data_hub_adapter.py` | FastAPI router with `POST /ingest/event` (HMAC-signed webhook), `POST /ingest/bulk`, `POST /ingest/dlq/replay`. `ingest_event(envelope)` is the pure-Python entry point. CLI: `python -m ingestion.data_hub_adapter --file backfill.jsonl`. |
| `schema_mapper.py` | Translates Data Hub envelope types (`invoice.paid`, `bill.created`, ...) to internal `EventName` constants. Raises `MalformedEnvelope` / `UnmappedEventType`. |
| `idempotency.py` | `was_seen(envelope_id)` + `mark_seen(...)` backed by `ingestion_seen` table. `to_dlq(envelope, reason, error)` + `replay_dlq(reason?, limit)` using `ingestion_dlq`. |
| `outbound.py` | Publishes `forecast.published` events back to Data Hub via HMAC-signed HTTP POST. Falls back to `reports/outbound/<date>.jsonl` when `DATA_HUB_URL` is unset or network fails. `register_outbound_publisher()` wires the subscription. |
| `__init__.py` | Re-exports `map_event`, `SUPPORTED_TYPES`, `data_hub_router`, `ingest_event`, `ingest_bulk`, `publish_outbound`, `register_outbound_publisher`. |

## Run individually

Webhook (needs API running):

```bash
python app/api.py
# then POST a signed envelope to http://localhost:8000/ingest/event
```

Bulk replay from JSONL:

```bash
python -m ingestion.data_hub_adapter --file backfill_2026_04.jsonl
```

Replay DLQ rows:

```bash
curl -X POST "http://localhost:8000/ingest/dlq/replay?reason=malformed&limit=50"
```

Outbound publisher test:

```python
from ingestion.outbound import publish
publish("forecast.published", {"run_id": "r1", "summary": "test"})
# writes to reports/outbound/<date>.jsonl when DATA_HUB_URL is unset
```

## Role in orchestration pipeline

**Inbound path:**
1. Data Hub sends envelope → `/ingest/event` webhook.
2. `data_hub_adapter.ingest_event` verifies idempotency, maps schema, emits to bus.
3. [events/listeners.py](../events/listeners.py) → `Scheduler.run_subgraph([...])`.
4. [orchestrator/volume_trigger.py](../orchestrator/volume_trigger.py) also counts the event.

**Outbound path:**
- After a pipeline run, someone emits `EventName.FORECAST_PUBLISHED` → `outbound.py` POSTs to Data Hub.

Failure → row in `ingestion_dlq`; retry via `/ingest/dlq/replay`.

## Required secrets

| Name | Purpose |
|------|---------|
| `DATA_HUB_SIGNING_KEY` | HMAC verification (inbound) + signing (outbound) |
| `DATA_HUB_URL` (optional) | If unset, outbound falls back to JSONL |

## Related

- Events: [events/triggers.py](../events/triggers.py) (event name catalogue).
- Tables: `ingestion_seen`, `ingestion_dlq` in [db/models.py](../db/models.py).
- Tenant scoping: [security/tenant_context.py](../security/tenant_context.py).
