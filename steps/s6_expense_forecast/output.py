"""
S6 Expense Forecast - Output
"""

import os
import logging
import yaml
import uuid
import pandas as pd
from pathlib import Path

logger = logging.getLogger("s6.output")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / "config" / "s6_expense_forecast.yml"


def _load_default_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def run(forecast_df, config=None, master_cfg=None):
    if config is None:
        config = _load_default_config()
    if master_cfg is None:
        master_cfg = {}

    logger.info("=" * 60)
    logger.info("S6 OUTPUT - START")
    logger.info("=" * 60)

    global_cfg = master_cfg.get("global", {})
    report_dir = BASE_DIR / global_cfg.get("report_dir", "reports") / "s6_expense_forecast"
    forecast_dir = BASE_DIR / "Data" / "forecast_outputs"
    os.makedirs(report_dir, exist_ok=True)
    os.makedirs(forecast_dir, exist_ok=True)

    if forecast_df.empty:
        logger.warning("No records to save")
        return {"status": "empty", "total_records": 0}

    # Save detailed
    detail_path = forecast_dir / "s6_expense_detail.csv"
    forecast_df.to_csv(detail_path, index=False)
    logger.info("Saved detail: %s (%d records)", detail_path, len(forecast_df))

    # Save unified forecast_outputs (outflows are negative)
    run_id = str(uuid.uuid4())
    fo = pd.DataFrame({
        "forecast_id": forecast_df["forecast_id"],
        "forecast_date": forecast_df["forecast_date"],
        "forecast_type": "EXPENSE",
        "target_date": forecast_df["expected_cash_date"],
        "forecast_amount": forecast_df["forecast_amount"],
        "confidence_low": forecast_df["forecast_amount"] * 1.1,  # more negative = wider low
        "confidence_high": forecast_df["forecast_amount"] * 0.9,
        "source_module": "S6",
        "forecast_run_id": run_id,
    })
    fo_path = forecast_dir / "s6_expense_forecast.csv"
    fo.to_csv(fo_path, index=False)
    logger.info("Saved forecast_outputs: %s (%d records)", fo_path, len(fo))

    # Summary
    summary = {
        "total_records": len(forecast_df),
        "total_outflow": round(abs(float(forecast_df["forecast_amount"].sum())), 2),
        "by_category": forecast_df.groupby("category")["forecast_amount"].sum().abs().round(2).to_dict(),
        "by_recurrence": forecast_df.groupby("recurrence_type")["forecast_amount"].sum().abs().round(2).to_dict(),
        "by_confidence": forecast_df.groupby("confidence_tier")["forecast_amount"].sum().abs().round(2).to_dict(),
    }

    logger.info("--- S6 Summary ---")
    logger.info("  Records: %d", summary["total_records"])
    logger.info("  Total outflow: $%s", f"{summary['total_outflow']:,.2f}")
    for cat, amt in summary["by_category"].items():
        logger.info("    %-18s $%s", cat, f"{amt:,.2f}")

    # Save summary
    rows = [
        {"Metric": "Total Records", "Value": summary["total_records"]},
        {"Metric": "Total Outflow", "Value": summary["total_outflow"]},
    ]
    for cat, amt in summary["by_category"].items():
        rows.append({"Metric": f"Category_{cat}", "Value": amt})
    pd.DataFrame(rows).to_csv(report_dir / "forecast_summary.csv", index=False)

    logger.info("=" * 60)
    logger.info("S6 OUTPUT - COMPLETE")
    logger.info("=" * 60)

    return summary
