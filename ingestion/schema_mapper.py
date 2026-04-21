"""
Data Hub -> Internal Schema Mapper
==================================
The Data Hub (client's in-build Postgres-backed aggregator) will push
events in a canonical JSON envelope:

    {
        "type": "invoice.created" | "bill.paid" | "customer.updated" | ...,
        "tenant_id": "entity_alpha",
        "occurred_at": "2026-04-21T10:15:00Z",
        "data": { ...payload fields... }
    }

This module translates the envelope to an internal EventName + payload
suitable for the event bus. Keeping the mapping here makes it easy to
evolve the Data Hub schema without touching the bus or listeners.
"""

import logging
from typing import Dict, Tuple

from events.triggers import EventName

logger = logging.getLogger(__name__)

SUPPORTED_TYPES = {
    "invoice.created":  EventName.INVOICE_CREATED,
    "invoice.updated":  EventName.INVOICE_UPDATED,
    "invoice.paid":     EventName.INVOICE_PAID,
    "bill.created":     EventName.BILL_CREATED,
    "bill.updated":     EventName.BILL_UPDATED,
    "bill.paid":        EventName.BILL_PAID,
    "customer.updated": EventName.CUSTOMER_UPDATED,
    "vendor.updated":   EventName.VENDOR_UPDATED,
}

REQUIRED_FIELDS = {"type", "tenant_id", "data"}


class UnmappedEventType(Exception):
    pass


class MalformedEnvelope(Exception):
    pass


def map_event(envelope: Dict) -> Tuple[str, str, Dict]:
    missing = REQUIRED_FIELDS - set(envelope.keys())
    if missing:
        raise MalformedEnvelope(f"missing fields: {sorted(missing)}")

    src_type = envelope["type"]
    internal = SUPPORTED_TYPES.get(src_type)
    if internal is None:
        raise UnmappedEventType(f"no mapping for type '{src_type}'")

    payload = dict(envelope["data"])
    payload["_source"] = "data_hub"
    payload["_occurred_at"] = envelope.get("occurred_at")

    return envelope["tenant_id"], internal, payload
