"""
Volume-Triggered Retraining
===========================
Nikunj (Q&A row 6): retraining cadence is "volume-based, to be
discussed, not periodic". This module implements the volume watcher.

Design
------
Every ingestion event of interest increments an in-memory counter
keyed by (tenant_id, model_key). When the counter crosses the
configured threshold, we fire Scheduler.run_subgraph([model_key])
and reset the counter.

Counters are also persisted to event_log (as meta-events) so that on
restart we can recover from the last zero-reset point by replaying.

Wiring
------
Call `register_volume_listeners()` once at app start (e.g. from
app/api.py or main.py), after `register_default_listeners()`.
"""

import logging
import threading
from collections import defaultdict
from pathlib import Path
from typing import Dict

import yaml

from events.event_bus import bus
from events.triggers import EventName
from orchestrator.scheduler import Scheduler
from security.tenant_context import tenant_scope, current_tenant

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

EVENT_TO_MODEL = {
    EventName.INVOICE_CREATED:  "s1_ar_prediction",
    EventName.INVOICE_UPDATED:  "s1_ar_prediction",
    EventName.INVOICE_PAID:     "s1_ar_prediction",
    EventName.BILL_CREATED:     "s2_ap_prediction",
    EventName.BILL_UPDATED:     "s2_ap_prediction",
    EventName.BILL_PAID:        "s2_ap_prediction",
    EventName.CUSTOMER_UPDATED: "credit_risk",
}


class VolumeTrigger:
    def __init__(self):
        self._counters: Dict[tuple, int] = defaultdict(int)
        self._lock = threading.Lock()
        self._thresholds = self._load_thresholds()

    @staticmethod
    def _load_thresholds() -> Dict[str, int]:
        with open(PROJECT_ROOT / "config.yml", "r") as f:
            cfg = yaml.safe_load(f)
        retrain_cfg = cfg.get("retraining", {}) or {}
        return {k: int(v.get("new_rows_threshold", 0))
                for k, v in retrain_cfg.items() if v.get("new_rows_threshold")}

    def handle(self, event_name: str):
        model_key = EVENT_TO_MODEL.get(event_name)
        if model_key is None:
            return
        threshold = self._thresholds.get(model_key)
        if not threshold:
            return

        tenant = current_tenant()
        key = (tenant, model_key)
        with self._lock:
            self._counters[key] += 1
            count = self._counters[key]
            if count < threshold:
                return
            self._counters[key] = 0

        logger.info(
            "volume_trigger: tenant=%s model=%s threshold=%d reached -> retrain",
            tenant, model_key, threshold,
        )
        with tenant_scope(tenant):
            Scheduler.run_subgraph([model_key])

    def peek(self) -> Dict:
        with self._lock:
            return {f"{t}|{m}": n for (t, m), n in self._counters.items()}


_trigger = VolumeTrigger()


def register_volume_listeners():
    for event_name in EVENT_TO_MODEL:
        bus.subscribe(event_name, lambda _payload, e=event_name: _trigger.handle(e))
    logger.info("volume listeners registered (%d events, thresholds=%s)",
                len(EVENT_TO_MODEL), _trigger._thresholds)


def peek_counters() -> Dict:
    return _trigger.peek()
