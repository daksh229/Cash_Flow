"""
Lineage Tracker
===============
Records data lineage: for every dataset produced, note the inputs that
generated it, the code version, and the config hash. Lets a reviewer
answer "where did this forecast number come from?" without re-running.

Lineage graph is stored as JSONL under reports/lineage.jsonl. Each line
is a directed edge plus metadata; downstream tooling can load it into
a graph DB when needed.
"""

import hashlib
import json
import os
import subprocess
import threading
from datetime import datetime
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DEFAULT_LINEAGE_PATH = PROJECT_ROOT / "reports" / "lineage.jsonl"
_lock = threading.Lock()


def _git_rev():
    try:
        return subprocess.check_output(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT, stderr=subprocess.DEVNULL,
        ).decode().strip()
    except Exception:
        return "unknown"


def _hash_config(cfg):
    if cfg is None:
        return None
    blob = json.dumps(cfg, sort_keys=True, default=str).encode()
    return hashlib.sha256(blob).hexdigest()[:12]


class LineageTracker:
    def __init__(self, path=None):
        self.path = Path(path or os.environ.get("CASHFLOW_LINEAGE_LOG", _DEFAULT_LINEAGE_PATH))
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def record(self, output, inputs, producer, run_id=None, config=None, **extra):
        entry = {
            "ts": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "run_id": run_id,
            "producer": producer,                     # e.g. "s1_ar_prediction"
            "output": output,                         # dataset/table/file id
            "inputs": list(inputs or []),             # upstream dataset ids
            "git_rev": _git_rev(),
            "config_hash": _hash_config(config),
            **extra,
        }
        line = json.dumps(entry, default=str)
        with _lock:
            with open(self.path, "a", encoding="utf-8") as f:
                f.write(line + "\n")
        return entry

    def trace(self, output, depth=10):
        """Walk the lineage backwards from `output` up to `depth` hops."""
        if not self.path.exists():
            return []
        with open(self.path, "r", encoding="utf-8") as f:
            records = [json.loads(ln) for ln in f if ln.strip()]
        by_output = {r["output"]: r for r in records}
        frontier, seen, trail = [output], set(), []
        for _ in range(depth):
            nxt = []
            for o in frontier:
                if o in seen or o not in by_output:
                    continue
                seen.add(o)
                r = by_output[o]
                trail.append(r)
                nxt.extend(r.get("inputs", []))
            if not nxt:
                break
            frontier = nxt
        return trail


lineage = LineageTracker()
