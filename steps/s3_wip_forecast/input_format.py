"""
S3 WIP Billing Forecast - Input Format
=========================================
Loads project milestones and customer payment features.
Filters to forecastable milestones (near completion or within lookforward window).
"""

import logging
import yaml
import pandas as pd
from pathlib import Path

logger = logging.getLogger("s3.input_format")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "Data"
CONFIG_PATH = BASE_DIR / "config" / "s3_wip_forecast.yml"


def _load_default_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def run(config=None):
    """
    Load project milestones and customer features, filter to forecastable milestones.

    Parameters
    ----------
    config : dict or None

    Returns
    -------
    pd.DataFrame : filtered milestones with customer payment delay attached
    """
    if config is None:
        config = _load_default_config()

    logger.info("=" * 60)
    logger.info("S3 INPUT FORMAT - START")
    logger.info("=" * 60)

    rules = config.get("rules", {})
    forecast_cfg = config.get("forecast", {})
    reference_date = pd.Timestamp(forecast_cfg.get("reference_date", "2026-04-15"))

    # ------------------------------------------------------------------
    # 1. Load project milestones
    # ------------------------------------------------------------------
    data_sources = config.get("data_sources", {})
    milestones_file = data_sources.get("project_milestones", "project_milestones.csv")
    milestones = pd.read_csv(DATA_DIR / milestones_file)
    milestones["expected_completion_date"] = pd.to_datetime(
        milestones["expected_completion_date"]
    )

    logger.info("Loaded project_milestones: %s", milestones.shape)
    logger.info("  Projects: %d", milestones["project_id"].nunique())
    logger.info("  Milestones: %d", len(milestones))
    logger.info(
        "  Completion status: %s",
        milestones["completion_status"].value_counts().to_dict(),
    )

    # ------------------------------------------------------------------
    # 2. Filter to active projects
    # ------------------------------------------------------------------
    include_statuses = rules.get("include_statuses", ["ACTIVE"])
    milestones = milestones[milestones["project_status"].isin(include_statuses)]
    logger.info("  After status filter (%s): %d", include_statuses, len(milestones))

    # ------------------------------------------------------------------
    # 3. Filter to forecastable milestones
    #    Include if: completion_pct >= threshold OR days_to_completion <= lookforward
    #    Exclude: already COMPLETE milestones (already billed)
    # ------------------------------------------------------------------
    completion_threshold = rules.get("completion_threshold", 0.80)
    lookforward_days = rules.get("lookforward_window_days", 30)

    # Exclude fully completed milestones (already invoiced)
    milestones = milestones[milestones["completion_status"] != "COMPLETE"]
    logger.info("  After excluding COMPLETE: %d", len(milestones))

    # Days to completion
    milestones["days_to_completion"] = (
        milestones["expected_completion_date"] - reference_date
    ).dt.days

    # Filter: near completion OR within lookforward window
    mask = (
        (milestones["completion_pct"] >= completion_threshold)
        | (
            (milestones["days_to_completion"] >= 0)
            & (milestones["days_to_completion"] <= lookforward_days)
        )
    )
    milestones = milestones[mask].copy()
    logger.info(
        "  After forecast filter (pct>=%.0f%% OR days<=%d): %d milestones",
        completion_threshold * 100, lookforward_days, len(milestones),
    )

    # Only billing-trigger milestones
    if "billing_trigger" in milestones.columns:
        milestones = milestones[milestones["billing_trigger"] == True]
        logger.info("  After billing_trigger filter: %d", len(milestones))

    # ------------------------------------------------------------------
    # 4. Load customer payment features (avg_payment_delay)
    # ------------------------------------------------------------------
    cust_features_file = data_sources.get(
        "customer_features", "features/customer_features.csv"
    )
    cust_features = pd.read_csv(DATA_DIR / cust_features_file)
    logger.info("Loaded customer_features: %s", cust_features.shape)

    # Merge avg_payment_delay onto milestones
    fallback_delay = rules.get("fallback_payment_delay_days", 30)

    milestones = milestones.merge(
        cust_features[["customer_id", "avg_payment_delay"]],
        on="customer_id",
        how="left",
    )
    # Fill missing with fallback
    no_history = milestones["avg_payment_delay"].isna().sum()
    milestones["customer_payment_delay"] = milestones["avg_payment_delay"].fillna(
        fallback_delay
    )
    # Ensure non-negative delay for cash date calc
    milestones["customer_payment_delay"] = milestones[
        "customer_payment_delay"
    ].clip(lower=0)

    logger.info(
        "  Customers with payment history: %d / %d (fallback used for %d)",
        len(milestones) - no_history, len(milestones), no_history,
    )

    logger.info("  Final shape: %s", milestones.shape)
    logger.info("  Columns: %s", list(milestones.columns))

    logger.info("=" * 60)
    logger.info("S3 INPUT FORMAT - COMPLETE")
    logger.info("=" * 60)

    return milestones


if __name__ == "__main__":
    df = run()
    print(f"Output shape: {df.shape}")
    print(df.head(10))
