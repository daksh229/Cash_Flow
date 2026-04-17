"""
Credit Risk Assessment - Input Format
=======================================
Loads customer_features for credit risk classification.
Target (risk_segment) is loaded from customer_payment_scores.
"""

import logging
import yaml
import pandas as pd
from pathlib import Path

logger = logging.getLogger("credit_risk.input_format")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
FEATURE_DIR = BASE_DIR / "Data" / "features"
CONFIG_PATH = BASE_DIR / "config" / "credit_risk.yml"


def _load_default_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def run(config=None):
    """
    Load customer_features and attach risk_segment target from
    customer_payment_scores.

    Parameters
    ----------
    config : dict or None

    Returns
    -------
    pd.DataFrame : customer features with risk_segment column
    """
    if config is None:
        config = _load_default_config()

    logger.info("=" * 60)
    logger.info("CREDIT RISK INPUT FORMAT - START")
    logger.info("=" * 60)

    # ------------------------------------------------------------------
    # 1. Load feature tables
    # ------------------------------------------------------------------
    feature_tables_needed = config.get("feature_tables", ["customer_features"])

    logger.info("Loading feature tables: %s", feature_tables_needed)
    loaded = {}
    for table_name in feature_tables_needed:
        path = FEATURE_DIR / f"{table_name}.csv"
        loaded[table_name] = pd.read_csv(path)
        logger.info("  %-30s %s", table_name, loaded[table_name].shape)

    merged = loaded["customer_features"].copy()
    logger.info("Base table: customer_features %s", merged.shape)

    # ------------------------------------------------------------------
    # 2. Attach target: risk_segment from customer_payment_scores
    # ------------------------------------------------------------------
    logger.info("Loading target from customer_payment_scores")
    target_cfg = config.get("target", {})
    derive_cfg = target_cfg.get("derive_from", {})
    source_table = derive_cfg.get("source_table", "customer_payment_scores.csv")
    target_col = derive_cfg.get("column", "risk_segment")

    scores = pd.read_csv(FEATURE_DIR / source_table)
    logger.info("  customer_payment_scores: %s", scores.shape)
    logger.info(
        "  risk_segment distribution: %s",
        scores["risk_segment"].value_counts().to_dict(),
    )

    merged = merged.merge(
        scores[["customer_id", target_col]], on="customer_id", how="inner"
    )
    logger.info("  After merge: %s", merged.shape)

    logger.info("  Final columns (%d): %s", len(merged.columns), list(merged.columns))

    logger.info("=" * 60)
    logger.info("CREDIT RISK INPUT FORMAT - COMPLETE")
    logger.info("=" * 60)

    return merged


if __name__ == "__main__":
    df = run()
    print(f"Output shape: {df.shape}")
