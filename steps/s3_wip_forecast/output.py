"""
S3 WIP Billing Forecast - Output
====================================
Saves forecast results and generates summary report.
"""

import os
import logging
import yaml
import pandas as pd
from pathlib import Path

logger = logging.getLogger("s3.output")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / "config" / "s3_wip_forecast.yml"


def _load_default_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def run(forecast_df, config=None, master_cfg=None):
    """
    Save forecast outputs and generate summary report.

    Parameters
    ----------
    forecast_df : pd.DataFrame
        Output from forecast_engine.run()
    config : dict or None
    master_cfg : dict or None

    Returns
    -------
    dict with summary statistics
    """
    if config is None:
        config = _load_default_config()
    if master_cfg is None:
        master_cfg = {}

    logger.info("=" * 60)
    logger.info("S3 OUTPUT - START")
    logger.info("=" * 60)

    global_cfg = master_cfg.get("global", {})
    report_dir = BASE_DIR / global_cfg.get("report_dir", "reports") / "s3_wip_forecast"
    forecast_dir = BASE_DIR / "Data" / "forecast_outputs"
    os.makedirs(report_dir, exist_ok=True)
    os.makedirs(forecast_dir, exist_ok=True)

    if forecast_df.empty:
        logger.warning("No forecast records to save")
        return {"status": "empty", "total_records": 0}

    # ------------------------------------------------------------------
    # 1. Save forecast outputs
    # ------------------------------------------------------------------
    forecast_path = forecast_dir / "s3_wip_forecast.csv"
    forecast_df.to_csv(forecast_path, index=False)
    logger.info("Saved forecast: %s (%d records)", forecast_path, len(forecast_df))

    # ------------------------------------------------------------------
    # 2. Generate summary report
    # ------------------------------------------------------------------
    summary = {}

    summary["total_milestones"] = len(forecast_df)
    summary["total_projects"] = forecast_df["project_id"].nunique()
    summary["total_customers"] = forecast_df["customer_id"].nunique()
    summary["total_forecast_amount"] = round(forecast_df["forecast_amount"].sum(), 2)
    summary["avg_forecast_amount"] = round(forecast_df["forecast_amount"].mean(), 2)

    # By confidence tier
    by_confidence = (
        forecast_df.groupby("confidence_tier")
        .agg(
            count=("forecast_id", "count"),
            total_amount=("forecast_amount", "sum"),
        )
        .to_dict("index")
    )
    summary["by_confidence"] = {
        k: {"count": v["count"], "total_amount": round(v["total_amount"], 2)}
        for k, v in by_confidence.items()
    }

    # By project type
    by_type = (
        forecast_df.groupby("project_type")
        .agg(
            count=("forecast_id", "count"),
            total_amount=("forecast_amount", "sum"),
        )
        .to_dict("index")
    )
    summary["by_project_type"] = {
        k: {"count": v["count"], "total_amount": round(v["total_amount"], 2)}
        for k, v in by_type.items()
    }

    # Weekly cash timeline
    forecast_df["cash_week"] = pd.to_datetime(
        forecast_df["expected_cash_date"]
    ).dt.to_period("W").astype(str)
    weekly = (
        forecast_df.groupby("cash_week")["forecast_amount"]
        .sum()
        .round(2)
        .to_dict()
    )
    summary["weekly_cash_inflow"] = weekly

    # ------------------------------------------------------------------
    # 3. Log summary
    # ------------------------------------------------------------------
    logger.info("--- S3 Forecast Summary ---")
    logger.info("  Milestones:       %d", summary["total_milestones"])
    logger.info("  Projects:         %d", summary["total_projects"])
    logger.info("  Customers:        %d", summary["total_customers"])
    logger.info("  Total forecast:   $%s", f"{summary['total_forecast_amount']:,.2f}")
    logger.info("  Avg per milestone:$%s", f"{summary['avg_forecast_amount']:,.2f}")

    logger.info("  By confidence:")
    for tier, vals in summary["by_confidence"].items():
        logger.info(
            "    %-8s %3d milestones  $%s",
            tier, vals["count"], f"{vals['total_amount']:,.2f}",
        )

    logger.info("  By project type:")
    for ptype, vals in summary["by_project_type"].items():
        logger.info(
            "    %-25s %3d milestones  $%s",
            ptype, vals["count"], f"{vals['total_amount']:,.2f}",
        )

    logger.info("  Weekly expected cash inflows:")
    for week, amount in sorted(weekly.items()):
        logger.info("    %-15s $%s", week, f"{amount:,.2f}")

    # Save summary as CSV
    summary_rows = [
        {"Metric": "Total Milestones", "Value": summary["total_milestones"]},
        {"Metric": "Total Projects", "Value": summary["total_projects"]},
        {"Metric": "Total Customers", "Value": summary["total_customers"]},
        {"Metric": "Total Forecast Amount", "Value": summary["total_forecast_amount"]},
        {"Metric": "Avg Forecast Amount", "Value": summary["avg_forecast_amount"]},
    ]
    for tier, vals in summary["by_confidence"].items():
        summary_rows.append(
            {"Metric": f"Confidence_{tier}_count", "Value": vals["count"]}
        )
        summary_rows.append(
            {"Metric": f"Confidence_{tier}_amount", "Value": vals["total_amount"]}
        )

    summary_df = pd.DataFrame(summary_rows)
    summary_path = report_dir / "forecast_summary.csv"
    summary_df.to_csv(summary_path, index=False)
    logger.info("  Summary saved: %s", summary_path)

    logger.info("=" * 60)
    logger.info("S3 OUTPUT - COMPLETE")
    logger.info("=" * 60)

    return summary


if __name__ == "__main__":
    from steps.s3_wip_forecast.input_format import run as input_run
    from steps.s3_wip_forecast.forecast_engine import run as engine_run

    milestones = input_run()
    forecast = engine_run(milestones)
    summary = run(forecast)
