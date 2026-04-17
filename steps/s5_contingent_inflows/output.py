"""
S5 Contingent Inflows - Output
"""

import os
import logging
import yaml
import uuid
import pandas as pd
from pathlib import Path

logger = logging.getLogger("s5.output")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / "config" / "s5_contingent_inflows.yml"


def _load_default_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def run(forecast_df, config=None, master_cfg=None):
    if config is None:
        config = _load_default_config()
    if master_cfg is None:
        master_cfg = {}

    logger.info("=" * 60)
    logger.info("S5 OUTPUT - START")
    logger.info("=" * 60)

    global_cfg = master_cfg.get("global", {})
    report_dir = BASE_DIR / global_cfg.get("report_dir", "reports") / "s5_contingent_inflows"
    forecast_dir = BASE_DIR / "Data" / "forecast_outputs"
    os.makedirs(report_dir, exist_ok=True)
    os.makedirs(forecast_dir, exist_ok=True)

    if forecast_df.empty:
        logger.warning("No records to save")
        return {"status": "empty", "total_records": 0}

    # Save detailed forecast
    detail_path = forecast_dir / "s5_contingent_detail.csv"
    forecast_df.to_csv(detail_path, index=False)
    logger.info("Saved detail: %s (%d records)", detail_path, len(forecast_df))

    # Save unified forecast_outputs
    run_id = str(uuid.uuid4())
    fo = pd.DataFrame({
        "forecast_id": forecast_df["forecast_id"],
        "forecast_date": forecast_df["forecast_date"],
        "forecast_type": "INFLOW",
        "target_date": forecast_df["expected_cash_date"],
        "forecast_amount": forecast_df["forecast_amount"],
        "confidence_low": forecast_df["forecast_amount"] * 0.8,
        "confidence_high": forecast_df["forecast_amount"] * 1.2,
        "source_module": "S5",
        "forecast_run_id": run_id,
    })
    fo_path = forecast_dir / "s5_contingent_forecast.csv"
    fo.to_csv(fo_path, index=False)
    logger.info("Saved forecast_outputs: %s (%d records)", fo_path, len(fo))

    # Summary
    summary = {
        "total_records": len(forecast_df),
        "total_forecast": round(float(forecast_df["forecast_amount"].sum()), 2),
        "by_category": forecast_df.groupby("category")["forecast_amount"].sum().round(2).to_dict(),
        "by_confidence": forecast_df.groupby("confidence_tier")["forecast_amount"].sum().round(2).to_dict(),
    }

    logger.info("--- S5 Summary ---")
    logger.info("  Records: %d", summary["total_records"])
    logger.info("  Total: $%s", f"{summary['total_forecast']:,.2f}")
    for cat, amt in summary["by_category"].items():
        logger.info("    %-15s $%s", cat, f"{amt:,.2f}")

    # Save summary
    rows = [
        {"Metric": "Total Records", "Value": summary["total_records"]},
        {"Metric": "Total Forecast", "Value": summary["total_forecast"]},
    ]
    for cat, amt in summary["by_category"].items():
        rows.append({"Metric": f"Category_{cat}", "Value": amt})
    pd.DataFrame(rows).to_csv(report_dir / "forecast_summary.csv", index=False)

    logger.info("=" * 60)
    logger.info("S5 OUTPUT - COMPLETE")
    logger.info("=" * 60)

    return summary
