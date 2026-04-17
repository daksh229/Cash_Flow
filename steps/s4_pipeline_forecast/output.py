"""
S4 Sales Pipeline Forecast - Output
=======================================
Saves forecast results in both detailed and forecast_outputs schema.
Generates summary report.
"""

import os
import logging
import yaml
import uuid
import pandas as pd
from pathlib import Path

logger = logging.getLogger("s4.output")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / "config" / "s4_pipeline_forecast.yml"


def _load_default_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def run(forecast_df, config=None, master_cfg=None):
    """
    Save forecast outputs and generate summary.
    """
    if config is None:
        config = _load_default_config()
    if master_cfg is None:
        master_cfg = {}

    logger.info("=" * 60)
    logger.info("S4 OUTPUT - START")
    logger.info("=" * 60)

    global_cfg = master_cfg.get("global", {})
    report_dir = BASE_DIR / global_cfg.get("report_dir", "reports") / "s4_pipeline_forecast"
    forecast_dir = BASE_DIR / "Data" / "forecast_outputs"
    os.makedirs(report_dir, exist_ok=True)
    os.makedirs(forecast_dir, exist_ok=True)

    if forecast_df.empty:
        logger.warning("No forecast records to save")
        return {"status": "empty", "total_records": 0}

    # ------------------------------------------------------------------
    # 1. Save detailed forecast
    # ------------------------------------------------------------------
    detail_path = forecast_dir / "s4_pipeline_detail.csv"
    forecast_df.to_csv(detail_path, index=False)
    logger.info("Saved detailed forecast: %s (%d records)", detail_path, len(forecast_df))

    # ------------------------------------------------------------------
    # 2. Save in unified forecast_outputs schema (for S7)
    # ------------------------------------------------------------------
    run_id = str(uuid.uuid4())
    fo = pd.DataFrame({
        "forecast_id": forecast_df["forecast_id"],
        "forecast_date": forecast_df["forecast_date"],
        "forecast_type": "PIPELINE",
        "target_date": forecast_df["expected_cash_date"],
        "forecast_amount": forecast_df["forecast_amount"],
        "confidence_low": forecast_df["forecast_amount"] * 0.7,
        "confidence_high": forecast_df["forecast_amount"] * 1.3,
        "source_module": "S4",
        "forecast_run_id": run_id,
    })
    fo_path = forecast_dir / "s4_pipeline_forecast.csv"
    fo.to_csv(fo_path, index=False)
    logger.info("Saved forecast_outputs: %s (%d records)", fo_path, len(fo))

    # ------------------------------------------------------------------
    # 3. Summary
    # ------------------------------------------------------------------
    summary = {
        "total_records": len(forecast_df),
        "total_deals": forecast_df["opportunity_id"].nunique(),
        "total_customers": forecast_df["customer_id"].nunique(),
        "total_forecast_amount": round(forecast_df["forecast_amount"].sum(), 2),
        "avg_per_milestone": round(forecast_df["forecast_amount"].mean(), 2),
    }

    # By stage
    by_stage = (
        forecast_df.groupby("crm_stage")
        .agg(count=("forecast_id", "count"), total=("forecast_amount", "sum"))
        .to_dict("index")
    )
    summary["by_stage"] = {
        k: {"count": v["count"], "total": round(v["total"], 2)}
        for k, v in by_stage.items()
    }

    # By deal type
    by_type = (
        forecast_df.groupby("deal_type")
        .agg(count=("forecast_id", "count"), total=("forecast_amount", "sum"))
        .to_dict("index")
    )
    summary["by_deal_type"] = {
        k: {"count": v["count"], "total": round(v["total"], 2)}
        for k, v in by_type.items()
    }

    # Monthly timeline
    forecast_df["cash_month"] = pd.to_datetime(
        forecast_df["expected_cash_date"]
    ).dt.to_period("M").astype(str)
    monthly = forecast_df.groupby("cash_month")["forecast_amount"].sum().round(2).to_dict()
    summary["monthly_cash_inflow"] = monthly

    # Log summary
    logger.info("--- S4 Forecast Summary ---")
    logger.info("  Deals:            %d", summary["total_deals"])
    logger.info("  Milestone records:%d", summary["total_records"])
    logger.info("  Customers:        %d", summary["total_customers"])
    logger.info("  Total forecast:   $%s", f"{summary['total_forecast_amount']:,.2f}")

    logger.info("  By stage:")
    for stage, vals in summary["by_stage"].items():
        logger.info(
            "    %-18s %3d records  $%s",
            stage, vals["count"], f"{vals['total']:,.2f}",
        )

    logger.info("  By deal type:")
    for dtype, vals in summary["by_deal_type"].items():
        logger.info(
            "    %-22s %3d records  $%s",
            dtype, vals["count"], f"{vals['total']:,.2f}",
        )

    logger.info("  Monthly expected cash:")
    for month, amount in sorted(monthly.items()):
        logger.info("    %-10s $%s", month, f"{amount:,.2f}")

    # Save summary
    summary_rows = [
        {"Metric": "Total Deals", "Value": summary["total_deals"]},
        {"Metric": "Total Records", "Value": summary["total_records"]},
        {"Metric": "Total Customers", "Value": summary["total_customers"]},
        {"Metric": "Total Forecast Amount", "Value": summary["total_forecast_amount"]},
    ]
    for stage, vals in summary["by_stage"].items():
        summary_rows.append({"Metric": f"Stage_{stage}_count", "Value": vals["count"]})
        summary_rows.append({"Metric": f"Stage_{stage}_amount", "Value": vals["total"]})

    pd.DataFrame(summary_rows).to_csv(report_dir / "forecast_summary.csv", index=False)
    logger.info("  Summary saved: %s", report_dir / "forecast_summary.csv")

    logger.info("=" * 60)
    logger.info("S4 OUTPUT - COMPLETE")
    logger.info("=" * 60)

    return summary


if __name__ == "__main__":
    from steps.s4_pipeline_forecast.input_format import run as input_run
    from steps.s4_pipeline_forecast.forecast_engine import run as engine_run

    data = input_run()
    forecast = engine_run(data)
    summary = run(forecast)
