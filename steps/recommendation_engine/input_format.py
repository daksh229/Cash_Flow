"""
Recommendation Engine - Input Format
========================================
Loads S7 cash position, S1/S2 predictions, customer scores, collections features.
"""

import logging
import yaml
import pandas as pd
from pathlib import Path

logger = logging.getLogger("re.input_format")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "Data"
CONFIG_PATH = BASE_DIR / "config" / "recommendation_engine.yml"


def _load_default_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def run(config=None):
    if config is None:
        config = _load_default_config()

    logger.info("=" * 60)
    logger.info("RECOMMENDATION ENGINE INPUT FORMAT - START")
    logger.info("=" * 60)

    sources = config.get("data_sources", {})
    data = {}

    # Load each source
    source_files = {
        "s7_daily": sources.get("s7_daily_position", "forecast_outputs/s7_daily_position.csv"),
        "s1_predictions": sources.get("s1_payment_predictions", "forecast_outputs/s1_payment_predictions.csv"),
        "s2_predictions": sources.get("s2_payment_predictions", "forecast_outputs/s2_payment_predictions.csv"),
        "customer_scores": sources.get("customer_payment_scores", "features/customer_payment_scores.csv"),
        "collections": sources.get("collections_features", "features/collections_features.csv"),
        "invoice_features": sources.get("invoice_features", "features/invoice_features.csv"),
        "invoices": sources.get("invoices", "invoices.csv"),
    }

    for key, filepath in source_files.items():
        full_path = DATA_DIR / filepath
        if full_path.exists():
            data[key] = pd.read_csv(full_path)
            logger.info("  Loaded %-20s %s", key, data[key].shape)
        else:
            logger.warning("  Missing: %s (%s)", key, full_path)
            data[key] = pd.DataFrame()

    # Parse dates
    if not data["s7_daily"].empty:
        data["s7_daily"]["date"] = pd.to_datetime(data["s7_daily"]["date"])

    if not data["s1_predictions"].empty:
        data["s1_predictions"]["predicted_payment_date"] = pd.to_datetime(
            data["s1_predictions"]["predicted_payment_date"]
        )

    # Build overdue invoices view (for collections lever)
    if not data["invoice_features"].empty and not data["invoices"].empty:
        inv = data["invoice_features"].copy()
        inv["due_date"] = pd.to_datetime(inv["due_date"])

        # Overdue = days_past_due > 0
        overdue = inv[inv["days_past_due"] > 0].copy()

        # Merge with collections features
        if not data["collections"].empty:
            overdue = overdue.merge(data["collections"], on="invoice_id", how="left")

        # Merge with customer scores
        if not data["customer_scores"].empty:
            overdue = overdue.merge(
                data["customer_scores"][["customer_id", "payment_score", "risk_segment"]],
                on="customer_id", how="left",
            )

        # Merge with S1 predictions for expected delay
        if not data["s1_predictions"].empty:
            overdue = overdue.merge(
                data["s1_predictions"][["transaction_id", "predicted_payment_date", "confidence_tier"]].rename(
                    columns={"transaction_id": "invoice_id", "confidence_tier": "prediction_confidence"}
                ),
                on="invoice_id", how="left",
            )

        data["overdue_invoices"] = overdue
        logger.info("  Overdue invoices: %d", len(overdue))
    else:
        data["overdue_invoices"] = pd.DataFrame()

    logger.info("=" * 60)
    logger.info("RECOMMENDATION ENGINE INPUT FORMAT - COMPLETE")
    logger.info("=" * 60)

    return data


if __name__ == "__main__":
    data = run()
    for k, v in data.items():
        if isinstance(v, pd.DataFrame):
            print(f"{k}: {v.shape}")
