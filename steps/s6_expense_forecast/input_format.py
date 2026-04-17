"""
S6 Expense Forecast - Input Format
"""

import logging
import yaml
import pandas as pd
from pathlib import Path

logger = logging.getLogger("s6.input_format")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "Data"
CONFIG_PATH = BASE_DIR / "config" / "s6_expense_forecast.yml"


def _load_default_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def run(config=None):
    if config is None:
        config = _load_default_config()

    logger.info("=" * 60)
    logger.info("S6 INPUT FORMAT - START")
    logger.info("=" * 60)

    data_sources = config.get("data_sources", {})
    forecast_cfg = config.get("forecast", {})
    reference_date = pd.Timestamp(forecast_cfg.get("reference_date", "2026-04-15"))
    horizon_days = forecast_cfg.get("horizon_days", 180)

    expenses = pd.read_csv(DATA_DIR / data_sources.get("expense_schedule", "expense_schedule.csv"))
    expenses["obligation_date"] = pd.to_datetime(expenses["obligation_date"])

    logger.info("Loaded expense_schedule: %s", expenses.shape)
    logger.info("  Categories: %s", expenses["category"].value_counts().to_dict())
    logger.info("  Recurrence: %s", expenses["recurrence_type"].value_counts().to_dict())

    # Filter to horizon
    horizon_end = reference_date + pd.Timedelta(days=horizon_days)
    expenses = expenses[
        (expenses["obligation_date"] >= reference_date)
        & (expenses["obligation_date"] <= horizon_end)
    ]
    logger.info("  After horizon filter: %d records", len(expenses))

    logger.info("=" * 60)
    logger.info("S6 INPUT FORMAT - COMPLETE")
    logger.info("=" * 60)

    return expenses


if __name__ == "__main__":
    df = run()
    print(f"Output: {df.shape}")
