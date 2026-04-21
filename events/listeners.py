"""
Event Listeners
===============
Wires event names to orchestrator actions. Import this module once at
application start (e.g. from main.py or app/api.py) to register all
default subscriptions.

Design note: listeners should stay thin. They decide WHICH subgraph to
re-run and delegate execution to Scheduler.run_subgraph. Heavy logic
belongs in steps/ or orchestrator/, not here.
"""

import logging

from events.event_bus import bus
from events.triggers import EventName
from orchestrator.scheduler import Scheduler

logger = logging.getLogger(__name__)


def _rescore_s1(payload):
    logger.info("S1 re-score triggered: %s", payload)
    Scheduler.run_subgraph(["s1_ar_prediction"])


def _rescore_s2(payload):
    logger.info("S2 re-score triggered: %s", payload)
    Scheduler.run_subgraph(["s2_ap_prediction"])


def _rescore_both(payload):
    logger.info("Customer/vendor change -> rebuild features + re-score: %s", payload)
    Scheduler.run_subgraph(["feature_table"])


def register_default_listeners():
    bus.subscribe(EventName.INVOICE_CREATED,  _rescore_s1)
    bus.subscribe(EventName.INVOICE_PAID,     _rescore_s1)
    bus.subscribe(EventName.INVOICE_UPDATED,  _rescore_s1)

    bus.subscribe(EventName.BILL_CREATED,     _rescore_s2)
    bus.subscribe(EventName.BILL_PAID,        _rescore_s2)
    bus.subscribe(EventName.BILL_UPDATED,     _rescore_s2)

    bus.subscribe(EventName.CUSTOMER_UPDATED, _rescore_both)
    bus.subscribe(EventName.VENDOR_UPDATED,   _rescore_both)

    logger.info("Registered default event listeners (%d events)",
                len(EventName.all()))
