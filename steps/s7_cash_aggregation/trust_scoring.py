"""
S7 - Source Trust Scoring
=========================
Assigns a trust weight per source_model, combining:
  - static baseline from config (e.g. deterministic S5 > ML S1)
  - recent accuracy from reports/ (test_mae / test_f1) if available
  - event-level confidence already present on each row

Trust becomes the tiebreaker when two sources report the same cash
event: higher-trust source wins during dedup.
"""

import json
import logging
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

DEFAULT_BASELINES = {
    "s1_ar_prediction":      0.75,
    "s2_ap_prediction":      0.80,
    "s3_wip_forecast":       0.70,
    "s4_pipeline_forecast":  0.60,
    "s5_contingent_inflows": 0.90,
    "s6_expense_forecast":   0.95,
}


def _latest_metric(model_key, metric_name):
    reports = sorted((PROJECT_ROOT / "reports").glob(f"{model_key}*metrics*.json"))
    if not reports:
        return None
    try:
        with open(reports[-1], "r") as f:
            return json.load(f).get(metric_name)
    except (OSError, json.JSONDecodeError):
        return None


def source_trust(model_key: str, baselines=None) -> float:
    baselines = baselines or DEFAULT_BASELINES
    base = baselines.get(model_key, 0.5)

    mae = _latest_metric(model_key, "test_mae")
    f1 = _latest_metric(model_key, "test_f1")

    if mae is not None:
        # lower MAE -> higher trust; squash into [0, 0.2] bump
        bonus = max(0.0, min(0.2, (10.0 - float(mae)) / 50.0))
        return round(min(1.0, base + bonus), 3)
    if f1 is not None:
        return round(min(1.0, base * 0.5 + float(f1) * 0.5), 3)
    return base


def annotate(events: pd.DataFrame, baselines=None) -> pd.DataFrame:
    out = events.copy()
    if out.empty:
        out["source_trust"] = []
        out["trust_score"] = []
        return out

    trust_by_source = {s: source_trust(s, baselines) for s in out["source_model"].unique()}
    out["source_trust"] = out["source_model"].map(trust_by_source)
    out["trust_score"] = (out["source_trust"] * out["confidence"]).round(4)
    logger.info("source trust: %s", trust_by_source)
    return out
