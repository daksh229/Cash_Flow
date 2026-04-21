"""
Model Selector (Auto-Rollback)
==============================
Serving-time decision: for each prediction request, pick the most
trustworthy artefact from:

  1. LightGBM (primary) - used when recent metrics haven't degraded
                           AND the entity has enough history
  2. RandomForest (baseline) - used when primary degraded > threshold
  3. GlobalPrior (cold-start) - used when entity has < min_customer_n rows

Degradation is measured by comparing the latest eval metric (test_mae
for regression, test_f1 for classification) against the rolling median
of the last N evaluations in reports/<model>*metrics*.json.

This module is pure logic - the ML pipeline writes the pickles, the
prior is fit separately. We just choose.
"""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

import joblib

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _load_metric_history(model_key: str, metric_name: str,
                        window: int = 3) -> List[float]:
    reports = sorted((PROJECT_ROOT / "reports").glob(f"{model_key}*metrics*.json"))
    values = []
    for p in reports[-window:]:
        try:
            with open(p, "r") as f:
                data = json.load(f)
            if metric_name in data:
                values.append(float(data[metric_name]))
        except (OSError, json.JSONDecodeError, ValueError):
            continue
    return values


def is_primary_degraded(model_key: str, metric_name: str,
                        latest: float, threshold_pct: float,
                        window: int = 3,
                        direction: str = "lower_is_better") -> bool:
    history = _load_metric_history(model_key, metric_name, window)
    if len(history) < 2:
        return False
    history_sorted = sorted(history)
    median = history_sorted[len(history_sorted) // 2]
    if median == 0:
        return False
    pct = (latest - median) / abs(median) * 100.0
    degraded = pct > threshold_pct if direction == "lower_is_better" \
        else pct < -threshold_pct
    if degraded:
        logger.warning(
            "model_selector: %s degraded (%s) latest=%.3f median=%.3f pct=%.1f%%",
            model_key, metric_name, latest, median, pct,
        )
    return degraded


def select(model_key: str, entity_stats: Dict, config: Dict) -> str:
    """Return one of: 'primary' | 'baseline' | 'prior'.

    If the model_registry has an explicit active variant for the
    current tenant, honour that. Otherwise fall back to metric-based
    selection so fresh deployments without registry entries still work.
    """
    try:
        from steps.shared.model_registry import active_variants
        actives = {a["variant"] for a in active_variants(model_key)}
    except Exception:
        actives = set()

    thin_threshold = int(config.get("evaluation", {}).get("thin_data_threshold", 10))
    n_history = int(entity_stats.get("n", 0))

    if n_history < max(1, config.get("cold_start", {}).get("min_customer_n", 3)):
        return "prior" if (not actives or "prior" in actives) else next(iter(actives))

    sel_cfg = config.get("model_selector", {})
    threshold_pct = float(sel_cfg.get("degradation_threshold_pct", 20))
    window = int(sel_cfg.get("comparison_window", 3))
    metric = "test_mae" if config.get("model_info", {}).get("type") == "regression" \
        else "test_f1"
    direction = "lower_is_better" if metric == "test_mae" else "higher_is_better"

    latest_history = _load_metric_history(model_key, metric, window=1)
    latest = latest_history[-1] if latest_history else None

    degraded = (latest is not None and is_primary_degraded(
        model_key, metric, latest, threshold_pct, window, direction,
    ))

    if degraded and ("baseline" in actives or not actives):
        return "baseline"

    if n_history < thin_threshold and ("baseline" in actives or not actives):
        return "baseline"

    if actives and "primary" not in actives:
        return next(iter(actives))
    return "primary"


def load_artifact(model_key: str, choice: str):
    """Load the selected artifact. Keep paths convention-based."""
    if choice == "primary":
        path = PROJECT_ROOT / "models" / f"{model_key}_lightgbm.pkl"
    elif choice == "baseline":
        path = PROJECT_ROOT / "models" / f"{model_key}_random_forest.pkl"
    else:
        path = PROJECT_ROOT / "models" / "cold_start_prior.pkl"
    if not path.exists():
        logger.warning("model_selector: artifact missing at %s", path)
        return None
    return joblib.load(path)


def predict(model_key: str, feature_row: Dict, entity_stats: Dict,
            config: Dict) -> Optional[Dict]:
    """One-shot: choose + load + predict on a single row."""
    choice = select(model_key, entity_stats, config)
    artifact = load_artifact(model_key, choice)
    if artifact is None:
        return {"prediction": None, "used": choice, "reason": "artifact_missing"}

    if choice == "prior":
        out = artifact.predict_one(feature_row) if hasattr(artifact, "predict_one") else None
        return {"prediction": out.get("predicted") if out else None,
                "used": choice, "detail": out}

    import pandas as pd
    X = pd.DataFrame([feature_row])
    try:
        y = artifact.predict(X)[0]
    except Exception as e:
        logger.error("model_selector predict failed: %s", e)
        return {"prediction": None, "used": choice, "error": str(e)}
    return {"prediction": float(y), "used": choice}
