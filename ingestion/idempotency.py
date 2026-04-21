"""
Ingestion Idempotency + Dead Letter Queue
=========================================
Data Hub will retry push on network/5xx failures. Without idempotency
we'd double-process the same invoice.created event.

Rules
-----
- Every envelope carries `envelope_id` (uuid from Data Hub). Missing
  ids are allowed but treated as always-new.
- `was_seen(envelope_id)` is the idempotency check - fast path.
- `mark_seen` records it atomically before dispatch.
- If schema_mapper or a handler fails, the envelope is written to the
  ingestion_dlq table with reason + error for later replay.

The DLQ table is a plain append-only log; operators inspect and
re-submit via `replay_dlq()`.
"""

import logging
from typing import Dict, List, Optional

from sqlalchemy.exc import IntegrityError

from db.connection import get_session
from db.models import IngestionDLQ, IngestionSeen

logger = logging.getLogger(__name__)


def was_seen(envelope_id: str) -> bool:
    if not envelope_id:
        return False
    with get_session() as s:
        return s.query(IngestionSeen.id).filter_by(envelope_id=envelope_id).first() is not None


def mark_seen(envelope_id: str, tenant_id: str = "default") -> bool:
    if not envelope_id:
        return True
    with get_session() as s:
        try:
            s.add(IngestionSeen(envelope_id=envelope_id, tenant_id=tenant_id))
            s.commit()
            return True
        except IntegrityError:
            s.rollback()
            return False


def to_dlq(envelope: Dict, reason: str, error: Optional[str] = None) -> int:
    with get_session() as s:
        row = IngestionDLQ(
            tenant_id=envelope.get("tenant_id") if isinstance(envelope, dict) else None,
            envelope_id=envelope.get("envelope_id") if isinstance(envelope, dict) else None,
            source_type=envelope.get("type") if isinstance(envelope, dict) else None,
            reason=reason,
            payload=envelope if isinstance(envelope, dict) else {"raw": str(envelope)},
            error=error,
        )
        s.add(row)
        s.commit()
        logger.warning("DLQ wrote id=%s reason=%s", row.id, reason)
        return row.id


def replay_dlq(reason_filter: Optional[str] = None,
               limit: int = 100) -> List[Dict]:
    """Re-submit DLQ rows through `ingest_event`. Rows that succeed
    are NOT deleted (the DLQ is append-only for audit); successful
    replays simply get picked up via new IngestionSeen rows."""
    from ingestion.data_hub_adapter import ingest_event

    with get_session() as s:
        q = s.query(IngestionDLQ)
        if reason_filter:
            q = q.filter(IngestionDLQ.reason == reason_filter)
        rows = q.order_by(IngestionDLQ.id).limit(limit).all()

    out = []
    for r in rows:
        try:
            res = ingest_event(r.payload)
            out.append({"dlq_id": r.id, "status": "requeued", "result": res})
        except Exception as e:
            out.append({"dlq_id": r.id, "status": "failed", "error": str(e)})
    logger.info("replay_dlq processed=%d", len(out))
    return out
