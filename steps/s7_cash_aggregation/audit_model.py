"""
S7 - Aggregation Audit Model
============================
Every S7 run should be explainable: "the 2026-05-10 forecast of X
came from these N events, with these K duplicates dropped, using
source trust Y." This module builds the per-run audit record that
joins the normalised events, dedup decisions, and trust weights.

The record is persisted two ways:
  - one RunAudit row (already written by the DAG) is tagged with a
    summary under RunAudit.error -> None + triggered_by
  - a detailed JSONL line per forecast bucket is appended under
    reports/s7_audit.jsonl, keyed by run_id, for downstream review
"""

import json
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

from audit.lineage_tracker import lineage

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_AUDIT_PATH = PROJECT_ROOT / "reports" / "s7_audit.jsonl"


def build(kept: pd.DataFrame, full_events: pd.DataFrame, run_id: str, config: dict) -> dict:
    _AUDIT_PATH.parent.mkdir(parents=True, exist_ok=True)

    by_source_input = full_events["source_model"].value_counts().to_dict() \
        if not full_events.empty else {}
    by_source_kept = kept["source_model"].value_counts().to_dict() \
        if not kept.empty else {}
    dropped_count = int(len(full_events) - len(kept))

    summary = {
        "run_id": run_id,
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "input_rows": int(len(full_events)),
        "kept_rows": int(len(kept)),
        "dropped_rows": dropped_count,
        "by_source_input": by_source_input,
        "by_source_kept": by_source_kept,
        "avg_trust_score": float(kept["trust_score"].mean()) if not kept.empty else None,
        "config_used": {
            k: config.get(k) for k in
            ["dedup_window_days", "amount_round", "trust_baselines"]
        },
    }

    with open(_AUDIT_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps(summary, default=str) + "\n")

    lineage.record(
        output="cash_forecast",
        inputs=sorted(by_source_input.keys()),
        producer="s7_cash_aggregation",
        run_id=run_id,
        config=config,
        kept_rows=summary["kept_rows"],
        dropped_rows=summary["dropped_rows"],
    )

    logger.info("S7 audit: kept=%d dropped=%d sources=%s",
                summary["kept_rows"], summary["dropped_rows"],
                list(by_source_input.keys()))
    return summary
