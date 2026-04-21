"""
Data Hub Ingestion Adapter
==========================
Two ingestion paths:

  1. Webhook (POST /ingest/event)       - real-time push from Data Hub
  2. Bulk (POST /ingest/bulk  or CLI)   - CSV/JSONL replay for backfills

Both paths go through schema_mapper and then into the event bus.
The bus persists every event to `event_log` (tenant-scoped) and
dispatches to listeners, which trigger the right DAG subgraph.

The webhook auths via an HMAC shared secret in X-Data-Hub-Signature
(Data Hub team will share the secret). That's independent of the user
bearer-token path so the Data Hub doesn't need a per-user token.

Mount in app/api.py:
    from ingestion import data_hub_router
    app.include_router(data_hub_router)
"""

import hashlib
import hmac
import json
import logging
from pathlib import Path
from typing import Dict, Iterable, List

from fastapi import APIRouter, Header, HTTPException, Request, status

from events.event_bus import bus
from ingestion.schema_mapper import (
    map_event, MalformedEnvelope, UnmappedEventType,
)
from ingestion.idempotency import was_seen, mark_seen, to_dlq
from security.secrets import get_secret
from security.tenant_context import tenant_scope

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/ingest", tags=["ingestion"])


def _verify_signature(raw_body: bytes, signature: str) -> bool:
    try:
        secret = get_secret("DATA_HUB_SIGNING_KEY")
    except KeyError:
        return False
    expected = hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature or "")


def ingest_event(envelope: Dict) -> Dict:
    """Dispatch a single Data Hub envelope to the event bus.

    Idempotent: duplicate envelope_ids are skipped. Schema or handler
    failures are written to the DLQ rather than propagated.
    """
    envelope_id = envelope.get("envelope_id") if isinstance(envelope, dict) else None
    if envelope_id and was_seen(envelope_id):
        return {"status": "duplicate", "envelope_id": envelope_id}

    try:
        tenant_id, internal, payload = map_event(envelope)
    except MalformedEnvelope as e:
        to_dlq(envelope, reason="malformed", error=str(e))
        return {"status": "dlq", "reason": "malformed", "error": str(e)}
    except UnmappedEventType as e:
        to_dlq(envelope, reason="unmapped", error=str(e))
        return {"status": "dlq", "reason": "unmapped", "error": str(e)}

    if envelope_id and not mark_seen(envelope_id, tenant_id):
        return {"status": "duplicate", "envelope_id": envelope_id}

    try:
        with tenant_scope(tenant_id):
            bus.emit(internal, payload)
    except Exception as e:
        to_dlq(envelope, reason="handler_error", error=str(e))
        return {"status": "dlq", "reason": "handler_error", "error": str(e)}

    return {"tenant_id": tenant_id, "event": internal,
            "envelope_id": envelope_id, "status": "queued"}


def ingest_bulk(envelopes: Iterable[Dict]) -> List[Dict]:
    return [ingest_event(env) for env in envelopes]


@router.post("/event", status_code=status.HTTP_202_ACCEPTED)
async def webhook(
    request: Request,
    x_data_hub_signature: str = Header(default=""),
):
    raw = await request.body()
    if not _verify_signature(raw, x_data_hub_signature):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "bad signature")
    try:
        envelope = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid json")
    return ingest_event(envelope)


@router.post("/dlq/replay", status_code=status.HTTP_200_OK)
def dlq_replay(reason: str = None, limit: int = 100):
    from ingestion.idempotency import replay_dlq
    return {"results": replay_dlq(reason_filter=reason, limit=limit)}


@router.post("/bulk", status_code=status.HTTP_202_ACCEPTED)
async def bulk(request: Request):
    raw = await request.body()
    try:
        envelopes = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "invalid json")
    if not isinstance(envelopes, list):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "expected a JSON array")
    return {"results": ingest_bulk(envelopes)}


def replay_jsonl(path: str) -> List[Dict]:
    """CLI helper to replay a JSONL file of envelopes (one per line)."""
    p = Path(path)
    with open(p, "r", encoding="utf-8") as f:
        envelopes = [json.loads(ln) for ln in f if ln.strip()]
    logger.info("replaying %d envelopes from %s", len(envelopes), p)
    return ingest_bulk(envelopes)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Data Hub bulk replay")
    parser.add_argument("--file", required=True, help="JSONL file of envelopes")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(replay_jsonl(args.file), default=str, indent=2))
