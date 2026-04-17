"""
Recommendation Engine - Output
"""

import os
import logging
import yaml
import pandas as pd
from pathlib import Path

logger = logging.getLogger("re.output")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / "config" / "recommendation_engine.yml"


def _load_default_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def run(rec_df, config=None, master_cfg=None):
    if config is None:
        config = _load_default_config()
    if master_cfg is None:
        master_cfg = {}

    logger.info("=" * 60)
    logger.info("RECOMMENDATION ENGINE OUTPUT - START")
    logger.info("=" * 60)

    global_cfg = master_cfg.get("global", {})
    report_dir = BASE_DIR / global_cfg.get("report_dir", "reports") / "recommendation_engine"
    forecast_dir = BASE_DIR / "Data" / "forecast_outputs"
    os.makedirs(report_dir, exist_ok=True)
    os.makedirs(forecast_dir, exist_ok=True)

    if rec_df.empty:
        logger.warning("No recommendations to save")
        return {"status": "empty", "total_recommendations": 0}

    # Save recommendations
    rec_path = forecast_dir / "recommendations.csv"
    rec_df.to_csv(rec_path, index=False)
    logger.info("Saved recommendations: %s (%d records)", rec_path, len(rec_df))

    # Summary
    summary = {
        "total_recommendations": len(rec_df),
        "total_cash_impact": round(float(rec_df["cash_impact"].sum()), 2),
        "by_lever": rec_df.groupby("lever").agg(
            count=("recommendation_id", "count"),
            cash_impact=("cash_impact", "sum"),
        ).round(2).to_dict("index"),
        "by_priority": rec_df["priority"].value_counts().to_dict(),
        "top_recommendations": [],
    }

    # Top recs for display
    for _, row in rec_df.head(10).iterrows():
        summary["top_recommendations"].append({
            "rank": int(row["rank"]),
            "lever": row["lever"],
            "entity_id": row["entity_id"],
            "action": row["action"],
            "description": row["description"],
            "cash_impact": round(float(row["cash_impact"]), 2),
            "score": round(float(row["score"]), 4),
            "priority": row["priority"],
        })

    # Log
    logger.info("--- Recommendation Summary ---")
    logger.info("  Total: %d recommendations", summary["total_recommendations"])
    logger.info("  Total cash impact: $%s", f"{summary['total_cash_impact']:,.2f}")
    logger.info("  By lever:")
    for lever, vals in summary["by_lever"].items():
        logger.info("    %-20s %d recs  $%s",
                     lever, vals["count"], f"{vals['cash_impact']:,.2f}")
    logger.info("  By priority: %s", summary["by_priority"])

    # Save summary
    rows = [
        {"Metric": "Total Recommendations", "Value": summary["total_recommendations"]},
        {"Metric": "Total Cash Impact", "Value": summary["total_cash_impact"]},
    ]
    for lever, vals in summary["by_lever"].items():
        rows.append({"Metric": f"Lever_{lever}_count", "Value": vals["count"]})
        rows.append({"Metric": f"Lever_{lever}_impact", "Value": vals["cash_impact"]})

    pd.DataFrame(rows).to_csv(report_dir / "recommendation_summary.csv", index=False)
    logger.info("  Summary saved: %s", report_dir / "recommendation_summary.csv")

    logger.info("=" * 60)
    logger.info("RECOMMENDATION ENGINE OUTPUT - COMPLETE")
    logger.info("=" * 60)

    return summary
