"""
Cash Accuracy KPI
=================
Nikunj weighted cash accuracy higher than days accuracy in Q&A row 7.
This module computes the composite cash-accuracy KPI from the latest
reconciliation summary and exposes it via Prometheus.

Score definition (0-100):
    cash_accuracy = (1 - clamp(mape_amount, 0, 1)) * 100

Composite KPI (what the client will look at):
    kpi = 0.7 * cash_accuracy + 0.3 * days_accuracy

where
    days_accuracy = max(0, 1 - mae_days / mae_days_target) * 100

Defaults are overridable in config.yml:
    kpi:
        cash_weight: 0.7
        days_weight: 0.3
        mae_days_target: 10
"""

import json
import logging
from pathlib import Path
from typing import Dict, Optional

import yaml

from monitoring.metrics import metrics

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
_RECON_DIR = PROJECT_ROOT / "reports" / "reconciliation"


def _weights_from_config() -> Dict:
    with open(PROJECT_ROOT / "config.yml", "r") as f:
        cfg = yaml.safe_load(f)
    kpi = cfg.get("kpi", {}) or {}
    return {
        "cash_weight": float(kpi.get("cash_weight", 0.7)),
        "days_weight": float(kpi.get("days_weight", 0.3)),
        "mae_days_target": float(kpi.get("mae_days_target", 10.0)),
    }


def _load_latest_summary(tenant_id: str, run_id: Optional[str]) -> Optional[Dict]:
    tag = run_id or "all"
    path = _RECON_DIR / f"{tenant_id}_{tag}.summary.json"
    if not path.exists():
        candidates = sorted(_RECON_DIR.glob(f"{tenant_id}_*.summary.json"))
        if not candidates:
            return None
        path = candidates[-1]
    with open(path, "r") as f:
        return json.load(f)


def compute(tenant_id: str = "default", run_id: Optional[str] = None) -> Optional[Dict]:
    summary = _load_latest_summary(tenant_id, run_id)
    if summary is None:
        logger.warning("cash_accuracy: no reconciliation summary for %s", tenant_id)
        return None

    w = _weights_from_config()
    mape = summary.get("mape_amount") or 0.0
    mae_days = summary.get("mae_days") or 0.0

    cash_accuracy = max(0.0, (1.0 - min(1.0, float(mape)))) * 100.0
    days_accuracy = max(0.0, 1.0 - float(mae_days) / w["mae_days_target"]) * 100.0
    kpi = w["cash_weight"] * cash_accuracy + w["days_weight"] * days_accuracy

    metrics.model_mae.labels(model=f"cash_kpi:{tenant_id}").set(round(kpi, 2))

    result = {
        "tenant_id": tenant_id,
        "run_id": summary.get("run_id"),
        "cash_accuracy": round(cash_accuracy, 2),
        "days_accuracy": round(days_accuracy, 2),
        "kpi": round(kpi, 2),
        "weights": w,
        "match_rate": summary.get("match_rate"),
    }
    logger.info("cash_accuracy tenant=%s kpi=%.2f", tenant_id, kpi)
    return result


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--tenant", default="default")
    parser.add_argument("--run-id")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    print(json.dumps(compute(args.tenant, args.run_id), indent=2))
