"""
Forecast <-> Actual Reconciliation
==================================
Closes the feedback loop Nikunj described in Q&A row 10:

  "In Data Hub we will create the schema where the actual collection
   date is from the ERP and forecasted date from this model is
   captured, and variance computed."

Flow:
  1. Data Hub (or manual bulk import) pushes realised cash events
     into ActualOutcome via `record_actual(...)`.
  2. `reconcile(run_id=...)` joins ActualOutcome with ForecastOutput
     on (tenant_id, reference_id), computes date and amount variance,
     writes per-row results to reports/reconciliation/<run_id>.csv,
     and rolls up a summary JSON for the monitoring layer to expose.

Metrics written to the summary (consumed by monitoring/cash_accuracy):
  - match_rate        : % forecasts with a corresponding actual
  - mae_days          : mean abs error in predicted vs actual date
  - mape_amount       : mean abs % error in predicted vs actual amount
  - bias_days         : signed mean error (positive = forecast late)
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import pandas as pd
from sqlalchemy import and_

from db.connection import get_session
from db.models import ActualOutcome, ForecastOutput
from security.tenant_context import current_tenant

logger = logging.getLogger(__name__)
PROJECT_ROOT = Path(__file__).resolve().parent.parent
_OUT_DIR = PROJECT_ROOT / "reports" / "reconciliation"


def record_actual(reference_id: str, source_type: str,
                  actual_date, actual_amount: float,
                  currency: str = "INR", payload: Optional[Dict] = None,
                  tenant_id: Optional[str] = None) -> int:
    tenant_id = tenant_id or current_tenant()
    with get_session() as s:
        row = ActualOutcome(
            tenant_id=tenant_id,
            reference_id=str(reference_id),
            source_type=source_type,
            actual_date=pd.to_datetime(actual_date).to_pydatetime(),
            actual_amount=float(actual_amount),
            currency=currency,
            payload=payload or {},
        )
        s.add(row)
        s.commit()
        return row.id


def _load_frames(tenant_id: str, run_id: Optional[str]):
    with get_session() as s:
        fq = s.query(ForecastOutput).filter(ForecastOutput.tenant_id == tenant_id)
        if run_id:
            fq = fq.filter(ForecastOutput.run_id == run_id)
        forecasts = pd.DataFrame([{
            "reference_id": r.reference_id,
            "source_model": r.source_model,
            "forecast_date": r.event_date,
            "forecast_amount": r.amount,
            "run_id": r.run_id,
        } for r in fq.all() if r.reference_id])

        actuals = pd.DataFrame([{
            "reference_id": r.reference_id,
            "source_type": r.source_type,
            "actual_date": r.actual_date,
            "actual_amount": r.actual_amount,
        } for r in s.query(ActualOutcome)
            .filter(ActualOutcome.tenant_id == tenant_id).all()])
    return forecasts, actuals


def reconcile(run_id: Optional[str] = None, tenant_id: Optional[str] = None) -> Dict:
    tenant_id = tenant_id or current_tenant()
    forecasts, actuals = _load_frames(tenant_id, run_id)

    if forecasts.empty:
        logger.warning("reconcile: no forecasts for tenant=%s run=%s", tenant_id, run_id)
        return {"tenant_id": tenant_id, "run_id": run_id,
                "match_rate": 0, "rows": 0}

    if actuals.empty:
        joined = forecasts.assign(
            actual_date=pd.NaT, actual_amount=None, source_type=None,
        )
    else:
        joined = forecasts.merge(actuals, on="reference_id", how="left")

    joined["date_error_days"] = (
        pd.to_datetime(joined["actual_date"]) - pd.to_datetime(joined["forecast_date"])
    ).dt.days
    joined["amount_error"] = joined["actual_amount"] - joined["forecast_amount"]
    joined["amount_pct_error"] = (
        joined["amount_error"].abs() / joined["forecast_amount"].abs()
    ).replace([float("inf"), -float("inf")], None)

    matched = joined.dropna(subset=["actual_date"])
    summary = {
        "tenant_id": tenant_id,
        "run_id": run_id,
        "generated_at": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "forecast_rows": int(len(joined)),
        "matched_rows": int(len(matched)),
        "match_rate": round(len(matched) / len(joined), 4) if len(joined) else 0,
        "mae_days": round(matched["date_error_days"].abs().mean(), 3)
            if not matched.empty else None,
        "bias_days": round(matched["date_error_days"].mean(), 3)
            if not matched.empty else None,
        "mape_amount": round(matched["amount_pct_error"].mean(), 4)
            if not matched.empty else None,
    }

    _OUT_DIR.mkdir(parents=True, exist_ok=True)
    tag = run_id or "all"
    joined.to_csv(_OUT_DIR / f"{tenant_id}_{tag}.csv", index=False)
    with open(_OUT_DIR / f"{tenant_id}_{tag}.summary.json", "w") as f:
        json.dump(summary, f, indent=2, default=str)
    logger.info("reconcile tenant=%s run=%s: %s", tenant_id, run_id, summary)
    return summary


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Forecast/Actual reconciliation")
    parser.add_argument("--run-id", help="restrict to one run")
    parser.add_argument("--tenant", help="tenant id (default: env/context)")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    out = reconcile(run_id=args.run_id, tenant_id=args.tenant)
    print(json.dumps(out, indent=2, default=str))
