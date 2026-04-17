"""
S3 WIP Billing Forecast - Forecast Engine
============================================
Rule-based deterministic forecast (Phase 1).
Applies the 5-step rule pipeline per milestone:
  1. Identify billable milestones (done in input_format)
  2. Assess completion proximity (done in input_format)
  3. Estimate invoice date = completion_date + invoice_lag
  4. Estimate cash date = invoice_date + customer_payment_delay
  5. Write forecast record
"""

import logging
import yaml
import uuid
import pandas as pd
import numpy as np
from pathlib import Path

logger = logging.getLogger("s3.forecast_engine")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / "config" / "s3_wip_forecast.yml"


def _load_default_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def run(milestones_df, config=None):
    """
    Apply rule-based forecast to each milestone.

    Parameters
    ----------
    milestones_df : pd.DataFrame
        Output from input_format.run() — filtered forecastable milestones
    config : dict or None

    Returns
    -------
    pd.DataFrame : forecast_outputs with one row per milestone
    """
    if config is None:
        config = _load_default_config()

    logger.info("=" * 60)
    logger.info("S3 FORECAST ENGINE - START")
    logger.info("=" * 60)

    rules = config.get("rules", {})
    forecast_cfg = config.get("forecast", {})

    reference_date = pd.Timestamp(forecast_cfg.get("reference_date", "2026-04-15"))
    horizon_days = forecast_cfg.get("horizon_days", 90)
    source_module = forecast_cfg.get("source_module", "S3")
    forecast_type = forecast_cfg.get("forecast_type", "WIP")
    invoice_lag = rules.get("default_invoice_lag_days", 7)

    df = milestones_df.copy()
    logger.info("Input milestones: %d", len(df))

    if len(df) == 0:
        logger.warning("No milestones to forecast")
        return pd.DataFrame()

    # ------------------------------------------------------------------
    # Step 3: Estimate invoice date
    # projected_completion_date: for IN_PROGRESS, estimate from pct
    # ------------------------------------------------------------------
    logger.info("Step 3: Estimating invoice dates (invoice_lag=%d days)", invoice_lag)

    df["expected_completion_date"] = pd.to_datetime(df["expected_completion_date"])

    # For IN_PROGRESS milestones, adjust completion date based on pct
    # If 90% done and expected completion is past, assume it finishes soon
    mask_in_progress = df["completion_status"] == "IN_PROGRESS"
    for idx in df[mask_in_progress].index:
        pct = df.loc[idx, "completion_pct"]
        expected = df.loc[idx, "expected_completion_date"]
        if expected < reference_date and pct >= 0.8:
            # Already past expected date but nearly done — assume finishes in remaining % * 7 days
            remaining_days = max(1, int((1 - pct) * 14))
            df.loc[idx, "projected_completion_date"] = reference_date + pd.Timedelta(
                days=remaining_days
            )
        else:
            df.loc[idx, "projected_completion_date"] = expected

    # For NOT_STARTED, use expected_completion_date as-is
    mask_not_started = df["completion_status"] == "NOT_STARTED"
    df.loc[mask_not_started, "projected_completion_date"] = df.loc[
        mask_not_started, "expected_completion_date"
    ]

    # Fill any remaining
    df["projected_completion_date"] = df["projected_completion_date"].fillna(
        df["expected_completion_date"]
    )

    # Invoice date = projected_completion + invoice_lag
    df["expected_invoice_date"] = df["projected_completion_date"] + pd.Timedelta(
        days=invoice_lag
    )

    logger.info("  Invoice dates computed")

    # ------------------------------------------------------------------
    # Step 4: Estimate cash date
    # expected_cash_date = invoice_date + customer_payment_delay
    # ------------------------------------------------------------------
    logger.info("Step 4: Estimating cash dates (customer-specific delay)")

    df["expected_cash_date"] = df["expected_invoice_date"] + pd.to_timedelta(
        df["customer_payment_delay"].astype(int), unit="D"
    )

    logger.info("  Cash dates computed")

    # ------------------------------------------------------------------
    # Step 5: Apply forecast horizon filter and assign confidence
    # ------------------------------------------------------------------
    horizon_end = reference_date + pd.Timedelta(days=horizon_days)

    # Only include cash dates within horizon
    before = len(df)
    df = df[df["expected_cash_date"] <= horizon_end].copy()
    logger.info(
        "  Horizon filter (within %d days): %d -> %d milestones",
        horizon_days, before, len(df),
    )

    # Confidence tier based on completion status and proximity
    def assign_confidence(row):
        if row["completion_pct"] >= 0.95:
            return "HIGH"
        elif row["completion_pct"] >= 0.80:
            return "MEDIUM"
        else:
            return "LOW"

    df["confidence_tier"] = df.apply(assign_confidence, axis=1)

    logger.info(
        "  Confidence distribution: %s",
        df["confidence_tier"].value_counts().to_dict(),
    )

    # ------------------------------------------------------------------
    # Build output in forecast_outputs schema
    # ------------------------------------------------------------------
    logger.info("Building forecast output records")

    forecast_records = []
    for _, row in df.iterrows():
        forecast_records.append({
            "forecast_id": str(uuid.uuid4()),
            "project_id": row["project_id"],
            "milestone_id": row["milestone_id"],
            "customer_id": row["customer_id"],
            "project_type": row.get("project_type", ""),
            "milestone_name": row["milestone_name"],
            "completion_pct": row["completion_pct"],
            "completion_status": row["completion_status"],
            "billing_amount": row["billing_amount"],
            "expected_completion_date": row["projected_completion_date"].strftime("%Y-%m-%d"),
            "expected_invoice_date": row["expected_invoice_date"].strftime("%Y-%m-%d"),
            "expected_cash_date": row["expected_cash_date"].strftime("%Y-%m-%d"),
            "forecast_amount": row["billing_amount"],
            "invoice_lag_days": invoice_lag,
            "customer_payment_delay_days": int(row["customer_payment_delay"]),
            "confidence_tier": row["confidence_tier"],
            "source_module": source_module,
            "forecast_type": forecast_type,
            "forecast_date": reference_date.strftime("%Y-%m-%d"),
        })

    output = pd.DataFrame(forecast_records)

    # Summary stats
    total_forecast = output["forecast_amount"].sum()
    logger.info("  Total milestones in forecast: %d", len(output))
    logger.info("  Total forecast amount: $%s", f"{total_forecast:,.2f}")
    logger.info("  Projects covered: %d", output["project_id"].nunique())
    logger.info("  Customers covered: %d", output["customer_id"].nunique())
    logger.info(
        "  Date range: %s to %s",
        output["expected_cash_date"].min(),
        output["expected_cash_date"].max(),
    )

    logger.info("=" * 60)
    logger.info("S3 FORECAST ENGINE - COMPLETE")
    logger.info("=" * 60)

    return output


if __name__ == "__main__":
    from steps.s3_wip_forecast.input_format import run as input_run

    milestones = input_run()
    forecast = run(milestones)
    print(f"\nForecast shape: {forecast.shape}")
    print(forecast.head(10).to_string())
