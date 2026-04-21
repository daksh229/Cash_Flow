"""
Logging Configuration
=====================
Structured JSON logging for production + human-readable logs for dev.
Selects format based on env var CASHFLOW_LOG_FORMAT (json|text).

Attaches a run_id via a LoggerAdapter so every log line from inside a
DAG run is greppable by run.
"""

import json
import logging
import os
import sys
from datetime import datetime


class JsonFormatter(logging.Formatter):
    def format(self, record):
        body = {
            "ts": datetime.utcfromtimestamp(record.created).isoformat(timespec="seconds") + "Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if record.exc_info:
            body["exc"] = self.formatException(record.exc_info)
        for k, v in record.__dict__.items():
            if k.startswith("ctx_"):
                body[k[4:]] = v
        return json.dumps(body, default=str)


def setup_logging(level=None, fmt=None):
    level = (level or os.environ.get("CASHFLOW_LOG_LEVEL", "INFO")).upper()
    fmt = fmt or os.environ.get("CASHFLOW_LOG_FORMAT", "text").lower()

    root = logging.getLogger()
    root.handlers.clear()
    handler = logging.StreamHandler(sys.stdout)

    if fmt == "json":
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s | %(name)s | %(levelname)s | %(message)s"
        ))
    root.addHandler(handler)
    root.setLevel(level)


def with_run_id(logger, run_id):
    """Return a LoggerAdapter that tags every record with ctx_run_id."""
    return logging.LoggerAdapter(logger, {"ctx_run_id": run_id})
