"""
S5 Contingent Inflows - Input Format
"""

import logging
import yaml
import pandas as pd
from pathlib import Path

logger = logging.getLogger("s5.input_format")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "Data"
CONFIG_PATH = BASE_DIR / "config" / "s5_contingent_inflows.yml"


def _load_default_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def run(config=None):
    if config is None:
        config = _load_default_config()

    logger.info("=" * 60)
    logger.info("S5 INPUT FORMAT - START")
    logger.info("=" * 60)

    data_sources = config.get("data_sources", {})
    forecast_cfg = config.get("forecast", {})
    reference_date = pd.Timestamp(forecast_cfg.get("reference_date", "2026-04-15"))
    horizon_days = forecast_cfg.get("horizon_days", 180)

    # Load contingent inflows
    inflows = pd.read_csv(DATA_DIR / data_sources.get("contingent_inflows", "contingent_inflows.csv"))
    inflows["expected_receipt_date"] = pd.to_datetime(inflows["expected_receipt_date"])

    logger.info("Loaded contingent_inflows: %s", inflows.shape)
    logger.info("  Categories: %s", inflows["category"].value_counts().to_dict())
    logger.info("  Approval: %s", inflows["approval_status"].value_counts().to_dict())

    # Filter to forecast horizon
    horizon_end = reference_date + pd.Timedelta(days=horizon_days)
    inflows = inflows[
        (inflows["expected_receipt_date"] >= reference_date)
        & (inflows["expected_receipt_date"] <= horizon_end)
    ]
    logger.info("  After horizon filter: %d records", len(inflows))

    logger.info("=" * 60)
    logger.info("S5 INPUT FORMAT - COMPLETE")
    logger.info("=" * 60)

    return inflows


if __name__ == "__main__":
    df = run()
    print(f"Output: {df.shape}")
