"""
S7 Cash Event Normalisation - Aggregation Engine
====================================================
Implements the 9-step S7 pipeline from the SDD:
  1. Ingest        (done in input_format)
  2. Standardise   (done in input_format)
  3. Apply Lags    (already applied by S1-S6)
  4. FX Conversion (Phase 1: single currency, skip)
  5. Deduplicate   (source priority rules)
  6. Assign Confidence Tier
  7. Aggregate     (daily, weekly, monthly gross and net)
  8. Cumulative Position (running balance from opening)
  9. Publish       (output tables)
"""

import logging
import yaml
import uuid
import pandas as pd
import numpy as np
from pathlib import Path

logger = logging.getLogger("s7.forecast_engine")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / "config" / "s7_cash_aggregation.yml"


def _load_default_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def run(input_data, config=None):
    if config is None:
        config = _load_default_config()

    logger.info("=" * 60)
    logger.info("S7 AGGREGATION ENGINE - START")
    logger.info("=" * 60)

    event_store = input_data["event_store"].copy()
    forecast_run_id = input_data["forecast_run_id"]

    forecast_cfg = config.get("forecast", {})
    reference_date = pd.Timestamp(forecast_cfg.get("reference_date", "2026-04-15"))
    opening_balance = config.get("opening", {}).get("cash_balance", 5000000.0)

    logger.info("Input events: %d", len(event_store))
    logger.info("Opening cash balance: $%s", f"{opening_balance:,.2f}")

    if event_store.empty:
        logger.warning("No events to aggregate")
        return {"event_store": event_store, "daily": pd.DataFrame(), "weekly": pd.DataFrame(), "monthly": pd.DataFrame()}

    event_store["target_date"] = pd.to_datetime(event_store["target_date"])
    event_store["forecast_amount"] = event_store["forecast_amount"].astype(float)

    # ------------------------------------------------------------------
    # Step 3: Apply Lags (already done by S1-S6, skip)
    # Step 4: FX Conversion (Phase 1: single currency, skip)
    # ------------------------------------------------------------------
    logger.info("Step 3-4: Lags already applied, FX skipped (single currency)")

    # ------------------------------------------------------------------
    # Step 5: Deduplicate
    # ------------------------------------------------------------------
    dedup_cfg = config.get("dedup", {})
    if dedup_cfg.get("enabled", True):
        logger.info("Step 5: Deduplication (source priority rules)")
        before = len(event_store)

        # Mark suppressed events
        event_store["suppressed"] = False
        event_store["suppression_reason"] = ""

        # For Phase 1: simple date-based dedup between overlapping sources
        # If S4 and S1 have events on same date, suppress S4
        # If S3 and S1 have events on same date, suppress S3
        # If S6 and S2 have events on same date for outflows, suppress S6

        for rule in dedup_cfg.get("rules", []):
            src_a = rule["source_a"]
            src_b = rule["source_b"]
            winner = rule["winner"]
            reason = rule["reason"]
            loser = src_a if winner == src_b else src_b

            # Find dates where both sources have events
            dates_a = set(
                event_store[event_store["source_module"] == src_a]["target_date"].dt.date
            )
            dates_b = set(
                event_store[event_store["source_module"] == src_b]["target_date"].dt.date
            )
            overlap_dates = dates_a & dates_b

            if overlap_dates:
                mask = (
                    (event_store["source_module"] == loser)
                    & (event_store["target_date"].dt.date.isin(overlap_dates))
                )
                event_store.loc[mask, "suppressed"] = True
                event_store.loc[mask, "suppression_reason"] = reason
                suppressed_count = mask.sum()
                if suppressed_count > 0:
                    logger.info(
                        "  Rule %s: suppressed %d %s events (%s wins)",
                        reason, suppressed_count, loser, winner,
                    )

        active_events = event_store[~event_store["suppressed"]].copy()
        logger.info(
            "  After dedup: %d active / %d suppressed / %d total",
            len(active_events),
            event_store["suppressed"].sum(),
            len(event_store),
        )
    else:
        active_events = event_store.copy()
        logger.info("Step 5: Dedup disabled")

    # ------------------------------------------------------------------
    # Step 6: Assign confidence tier (already set by source modules)
    # ------------------------------------------------------------------
    logger.info("Step 6: Confidence tiers already assigned by source modules")
    logger.info(
        "  Distribution: %s",
        active_events["confidence_tier"].value_counts().to_dict(),
    )

    # ------------------------------------------------------------------
    # Step 7: Aggregate (daily, weekly, monthly)
    # ------------------------------------------------------------------
    logger.info("Step 7: Aggregating into daily/weekly/monthly views")

    # Separate inflows and outflows
    inflows = active_events[active_events["forecast_amount"] > 0].copy()
    outflows = active_events[active_events["forecast_amount"] < 0].copy()

    # --- Daily aggregation ---
    date_range = pd.date_range(
        start=reference_date,
        end=active_events["target_date"].max(),
        freq="D",
    )

    daily_inflow = (
        inflows.groupby(inflows["target_date"].dt.date)["forecast_amount"]
        .sum()
        .reindex(date_range.date, fill_value=0)
    )
    daily_outflow = (
        outflows.groupby(outflows["target_date"].dt.date)["forecast_amount"]
        .sum()
        .abs()
        .reindex(date_range.date, fill_value=0)
    )

    daily = pd.DataFrame({
        "date": date_range.date,
        "gross_inflow": daily_inflow.values,
        "gross_outflow": daily_outflow.values,
    })
    daily["net_flow"] = daily["gross_inflow"] - daily["gross_outflow"]

    # ------------------------------------------------------------------
    # Step 8: Cumulative position (running balance)
    # ------------------------------------------------------------------
    logger.info("Step 8: Computing cumulative cash position")
    daily["cumulative_position"] = opening_balance + daily["net_flow"].cumsum()
    daily["date"] = pd.to_datetime(daily["date"])

    # --- Weekly aggregation ---
    weekly = daily.copy()
    weekly["week"] = weekly["date"].dt.to_period("W").astype(str)
    weekly = (
        weekly.groupby("week")
        .agg(
            gross_inflow=("gross_inflow", "sum"),
            gross_outflow=("gross_outflow", "sum"),
            net_flow=("net_flow", "sum"),
            closing_position=("cumulative_position", "last"),
        )
        .round(2)
        .reset_index()
    )

    # --- Monthly aggregation ---
    monthly = daily.copy()
    monthly["month"] = monthly["date"].dt.to_period("M").astype(str)
    monthly = (
        monthly.groupby("month")
        .agg(
            gross_inflow=("gross_inflow", "sum"),
            gross_outflow=("gross_outflow", "sum"),
            net_flow=("net_flow", "sum"),
            closing_position=("cumulative_position", "last"),
        )
        .round(2)
        .reset_index()
    )

    # Summary stats
    logger.info("  Daily records: %d", len(daily))
    logger.info("  Weekly records: %d", len(weekly))
    logger.info("  Monthly records: %d", len(monthly))
    logger.info(
        "  Total inflows: $%s", f"{daily['gross_inflow'].sum():,.2f}"
    )
    logger.info(
        "  Total outflows: $%s", f"{daily['gross_outflow'].sum():,.2f}"
    )
    logger.info(
        "  Net position change: $%s", f"{daily['net_flow'].sum():,.2f}"
    )
    logger.info(
        "  Opening balance: $%s", f"{opening_balance:,.2f}"
    )
    logger.info(
        "  Closing balance: $%s", f"{daily['cumulative_position'].iloc[-1]:,.2f}"
    )

    # Min cash position
    min_pos = daily["cumulative_position"].min()
    min_date = daily.loc[daily["cumulative_position"].idxmin(), "date"]
    logger.info(
        "  Minimum cash position: $%s on %s",
        f"{min_pos:,.2f}", min_date.date(),
    )

    logger.info("=" * 60)
    logger.info("S7 AGGREGATION ENGINE - COMPLETE")
    logger.info("=" * 60)

    return {
        "event_store": event_store,
        "active_events": active_events,
        "daily": daily,
        "weekly": weekly,
        "monthly": monthly,
        "opening_balance": opening_balance,
        "forecast_run_id": forecast_run_id,
    }


if __name__ == "__main__":
    from steps.s7_cash_aggregation.input_format import run as input_run
    data = input_run()
    result = run(data)
    print(f"Daily: {result['daily'].shape}")
    print(result["daily"].head(10))
