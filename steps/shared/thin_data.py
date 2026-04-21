"""
Thin-Data Split Analyser
========================
Nikunj (Q1): a meaningful share of customers/vendors will have fewer
than 10 transactions. LightGBM overfits on those rows and its per-row
accuracy misleads the global metric.

This module splits predictions by row-level history depth and returns
per-bucket metrics so training/eval code can log them and so downstream
MLflow can track drift in each bucket independently.

Columns expected on X_test:
    invoice_count (for S1 customers) OR any numeric "count" feature.
"""

import logging
from typing import Dict, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def split_metrics(X_test: pd.DataFrame, y_true, y_pred,
                  threshold: int, count_col: str = "invoice_count",
                  label: str = "thin") -> Optional[Dict]:
    if X_test is None or y_pred is None or count_col not in X_test.columns:
        return None
    mask = X_test[count_col] < threshold
    if not mask.any():
        return None

    y_true = np.asarray(y_true)
    y_pred = np.asarray(y_pred)

    thin_mae = float(np.mean(np.abs(y_true[mask] - y_pred[mask])))
    rich_mae = (float(np.mean(np.abs(y_true[~mask] - y_pred[~mask])))
                if (~mask).any() else None)
    out = {
        f"{label}_data_mae":  round(thin_mae, 3),
        f"rich_data_mae":     round(rich_mae, 3) if rich_mae is not None else None,
        f"{label}_data_n":    int(mask.sum()),
        "rich_data_n":        int((~mask).sum()),
        "threshold":          int(threshold),
        "count_column":       count_col,
    }
    logger.info(
        "thin_data_split[%s]: thin(<%d)=%d mae=%.2f | rich(>=%d)=%d mae=%s",
        label, threshold, out[f"{label}_data_n"], thin_mae,
        threshold, out["rich_data_n"],
        "n/a" if rich_mae is None else f"{rich_mae:.2f}",
    )
    return out


def log_to_mlflow(metrics: Dict, mlflow_mod=None):
    if metrics is None or mlflow_mod is None:
        return
    for k, v in metrics.items():
        if isinstance(v, (int, float)) and v is not None:
            try:
                mlflow_mod.log_metric(k, float(v))
            except Exception:
                pass
