"""
Outbound Publisher -> Data Hub
==============================
Inbound adapter handles Data Hub -> us. This module handles us -> Data
Hub, so the rest of the client's ecosystem (dashboards, oncall alerts,
other consumers) sees fresh forecasts and reconciliation summaries.

Two delivery modes:
  - HTTP POST    : fire-and-forget to DATA_HUB_URL + HMAC signature
  - Local JSONL  : appends to reports/outbound/<date>.jsonl as a
                   replayable fallback when the URL isn't configured.

Publication is triggered by subscribing `_on_forecast_published` to
the `forecast.published` event. S7 (or whichever module closes the run)
emits that event with the run_id and summary.

Wire once at startup:
    from ingestion.outbound import register_outbound_publisher
    register_outbound_publisher()
"""

import hashlib
import hmac
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Dict

import requests

from events.event_bus import bus
from events.triggers import EventName
from security.secrets import get_secret
from security.tenant_context import current_tenant

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
_LOCAL_DIR = PROJECT_ROOT / "reports" / "outbound"


def _sign(body: bytes) -> str:
    try:
        secret = get_secret("DATA_HUB_SIGNING_KEY")
    except KeyError:
        return ""
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def publish(event_type: str, data: Dict) -> Dict:
    envelope = {
        "type": event_type,
        "tenant_id": current_tenant(),
        "occurred_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "data": data,
    }
    raw = json.dumps(envelope, default=str).encode()

    url = os.environ.get("DATA_HUB_URL")
    if url:
        try:
            r = requests.post(
                url, data=raw,
                headers={
                    "Content-Type": "application/json",
                    "X-Cashflow-Signature": _sign(raw),
                },
                timeout=5,
            )
            logger.info("outbound POST %s -> %s", event_type, r.status_code)
            return {"mode": "http", "status_code": r.status_code}
        except requests.RequestException as e:
            logger.warning("outbound POST failed (%s); falling back to local", e)

    _LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    path = _LOCAL_DIR / f"{datetime.utcnow().strftime('%Y-%m-%d')}.jsonl"
    with open(path, "a", encoding="utf-8") as f:
        f.write(raw.decode() + "\n")
    return {"mode": "local", "path": str(path)}


def _on_forecast_published(payload: Dict):
    publish("forecast.published", payload or {})


def register_outbound_publisher():
    bus.subscribe(EventName.FORECAST_PUBLISHED, _on_forecast_published)
    logger.info("outbound publisher registered for %s", EventName.FORECAST_PUBLISHED)
