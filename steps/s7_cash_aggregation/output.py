"""
S7 Cash Event Normalisation - Output
=========================================
Step 9: Publish — saves normalised event store, time-series views,
and summary report.
"""

import os
import logging
import yaml
import uuid
import pandas as pd
from pathlib import Path

logger = logging.getLogger("s7.output")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / "config" / "s7_cash_aggregation.yml"


def _load_default_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def run(engine_result, config=None, master_cfg=None):
    if config is None:
        config = _load_default_config()
    if master_cfg is None:
        master_cfg = {}

    logger.info("=" * 60)
    logger.info("S7 OUTPUT (Step 9: Publish) - START")
    logger.info("=" * 60)

    global_cfg = master_cfg.get("global", {})
    report_dir = BASE_DIR / global_cfg.get("report_dir", "reports") / "s7_cash_aggregation"
    forecast_dir = BASE_DIR / "Data" / "forecast_outputs"
    os.makedirs(report_dir, exist_ok=True)
    os.makedirs(forecast_dir, exist_ok=True)

    event_store = engine_result["event_store"]
    active_events = engine_result["active_events"]
    daily = engine_result["daily"]
    weekly = engine_result["weekly"]
    monthly = engine_result["monthly"]
    opening_balance = engine_result["opening_balance"]
    forecast_run_id = engine_result["forecast_run_id"]

    # ------------------------------------------------------------------
    # 1. Save normalised event store (all events incl. suppressed)
    # ------------------------------------------------------------------
    event_path = forecast_dir / "s7_event_store.csv"
    event_store.to_csv(event_path, index=False)
    logger.info("Saved event store: %s (%d events)", event_path, len(event_store))

    # ------------------------------------------------------------------
    # 2. Save time-series views
    # ------------------------------------------------------------------
    daily_path = forecast_dir / "s7_daily_position.csv"
    daily.to_csv(daily_path, index=False)
    logger.info("Saved daily position: %s (%d days)", daily_path, len(daily))

    weekly_path = forecast_dir / "s7_weekly_position.csv"
    weekly.to_csv(weekly_path, index=False)
    logger.info("Saved weekly position: %s (%d weeks)", weekly_path, len(weekly))

    monthly_path = forecast_dir / "s7_monthly_position.csv"
    monthly.to_csv(monthly_path, index=False)
    logger.info("Saved monthly position: %s (%d months)", monthly_path, len(monthly))

    # ------------------------------------------------------------------
    # 3. Save unified forecast_outputs (CASH type)
    # ------------------------------------------------------------------
    fo = pd.DataFrame({
        "forecast_id": [str(uuid.uuid4()) for _ in range(len(daily))],
        "forecast_date": daily["date"].iloc[0].strftime("%Y-%m-%d") if len(daily) > 0 else "",
        "forecast_type": "CASH",
        "target_date": daily["date"].dt.strftime("%Y-%m-%d"),
        "forecast_amount": daily["net_flow"],
        "confidence_low": daily["net_flow"] * 0.85,
        "confidence_high": daily["net_flow"] * 1.15,
        "source_module": "S7",
        "forecast_run_id": forecast_run_id,
    })
    fo_path = forecast_dir / "s7_cash_forecast.csv"
    fo.to_csv(fo_path, index=False)
    logger.info("Saved forecast_outputs (CASH): %s (%d records)", fo_path, len(fo))

    # ------------------------------------------------------------------
    # 4. Summary report
    # ------------------------------------------------------------------
    summary = {
        "forecast_run_id": forecast_run_id,
        "opening_balance": opening_balance,
        "total_events": len(event_store),
        "active_events": len(active_events),
        "suppressed_events": int(event_store["suppressed"].sum()) if "suppressed" in event_store.columns else 0,
        "total_inflows": round(float(daily["gross_inflow"].sum()), 2),
        "total_outflows": round(float(daily["gross_outflow"].sum()), 2),
        "net_position_change": round(float(daily["net_flow"].sum()), 2),
        "closing_balance": round(float(daily["cumulative_position"].iloc[-1]), 2) if len(daily) > 0 else opening_balance,
        "min_cash_position": round(float(daily["cumulative_position"].min()), 2) if len(daily) > 0 else opening_balance,
        "min_cash_date": str(daily.loc[daily["cumulative_position"].idxmin(), "date"].date()) if len(daily) > 0 else "",
        "forecast_days": len(daily),
    }

    # By source
    if len(active_events) > 0:
        by_source = (
            active_events.groupby("source_module")["forecast_amount"]
            .agg(["count", "sum"])
            .round(2)
            .to_dict("index")
        )
        summary["by_source"] = {
            k: {"count": int(v["count"]), "total": round(v["sum"], 2)}
            for k, v in by_source.items()
        }

    # Monthly view for summary
    summary["monthly_net"] = monthly.set_index("month")["net_flow"].to_dict()
    summary["monthly_closing"] = monthly.set_index("month")["closing_position"].to_dict()

    # Log summary
    logger.info("=" * 60)
    logger.info("S7 CASH FORECAST SUMMARY")
    logger.info("=" * 60)
    logger.info("  Run ID:           %s", summary["forecast_run_id"])
    logger.info("  Opening balance:  $%s", f"{summary['opening_balance']:,.2f}")
    logger.info("  Total inflows:    $%s", f"{summary['total_inflows']:,.2f}")
    logger.info("  Total outflows:   $%s", f"{summary['total_outflows']:,.2f}")
    logger.info("  Net change:       $%s", f"{summary['net_position_change']:,.2f}")
    logger.info("  Closing balance:  $%s", f"{summary['closing_balance']:,.2f}")
    logger.info("  Min cash:         $%s on %s", f"{summary['min_cash_position']:,.2f}", summary["min_cash_date"])
    logger.info("  Events: %d total, %d active, %d suppressed",
                summary["total_events"], summary["active_events"], summary["suppressed_events"])

    logger.info("  By source module:")
    for src, vals in summary.get("by_source", {}).items():
        direction = "inflow" if vals["total"] > 0 else "outflow"
        logger.info("    %-6s %4d events  $%s (%s)",
                     src, vals["count"], f"{abs(vals['total']):,.2f}", direction)

    logger.info("  Monthly net cash flow:")
    for month, net in summary.get("monthly_net", {}).items():
        closing = summary["monthly_closing"].get(month, 0)
        logger.info("    %-8s net: $%s  closing: $%s",
                     month, f"{net:>12,.2f}", f"{closing:>12,.2f}")

    # Save summary CSV
    summary_rows = [
        {"Metric": "Opening Balance", "Value": summary["opening_balance"]},
        {"Metric": "Total Inflows", "Value": summary["total_inflows"]},
        {"Metric": "Total Outflows", "Value": summary["total_outflows"]},
        {"Metric": "Net Position Change", "Value": summary["net_position_change"]},
        {"Metric": "Closing Balance", "Value": summary["closing_balance"]},
        {"Metric": "Min Cash Position", "Value": summary["min_cash_position"]},
        {"Metric": "Min Cash Date", "Value": summary["min_cash_date"]},
        {"Metric": "Total Events", "Value": summary["total_events"]},
        {"Metric": "Active Events", "Value": summary["active_events"]},
        {"Metric": "Suppressed Events", "Value": summary["suppressed_events"]},
    ]
    for month, net in summary.get("monthly_net", {}).items():
        summary_rows.append({"Metric": f"Monthly_Net_{month}", "Value": net})

    pd.DataFrame(summary_rows).to_csv(report_dir / "cash_forecast_summary.csv", index=False)
    logger.info("  Summary saved: %s", report_dir / "cash_forecast_summary.csv")

    logger.info("=" * 60)
    logger.info("S7 OUTPUT - COMPLETE")
    logger.info("=" * 60)

    return summary
