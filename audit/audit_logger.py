"""
Audit Logger
============
Structured audit trail for pipeline actions. Complements RunAudit (which
captures run-level start/finish) by recording fine-grained events:
  - config hash used
  - which model versions were trained
  - who/what triggered a run
  - accept/reject decisions in the recommendation engine

Writes to a dedicated JSONL file (append-only) and mirrors the key fields
into stdout via the standard logger. JSONL is used so downstream SIEM
tooling can ingest it without a parser.
"""

import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent

_DEFAULT_AUDIT_PATH = PROJECT_ROOT / "reports" / "audit.jsonl"
_lock = threading.Lock()


class AuditLogger:
    def __init__(self, path=None):
        self.path = Path(path or os.environ.get("CASHFLOW_AUDIT_LOG", _DEFAULT_AUDIT_PATH))
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, action, actor=None, run_id=None, **fields):
        entry = {
            "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "action": action,
            "actor": actor or os.environ.get("USER") or "system",
            "run_id": run_id,
            **fields,
        }
        line = json.dumps(entry, default=str)
        with _lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        logger.info("AUDIT | %s", line)
        return entry

    def tail(self, n=50):
        if not self.path.exists():
            return []
        with open(self.path, "r", encoding="utf-8") as f:
            lines = f.readlines()[-n:]
        return [json.loads(ln) for ln in lines if ln.strip()]


audit = AuditLogger()
