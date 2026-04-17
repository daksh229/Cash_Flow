"""
S1 AR Collections Prediction - Input Format
=============================================
Loads feature tables relevant to S1, merges them into a single
DataFrame ready for preprocessing.

Reads configuration from model config (passed by main.py or used standalone).
"""

import logging
import yaml
import pandas as pd
from pathlib import Path

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------
logger = logging.getLogger("s1.input_format")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent
FEATURE_DIR = BASE_DIR / "Data" / "features"
CONFIG_PATH = BASE_DIR / "config" / "s1_ar_prediction.yml"


def _load_default_config():
    """Load config from file when running standalone."""
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def run(config=None):
    """
    Load and merge feature tables for S1 AR prediction.

    Parameters
    ----------
    config : dict or None
        Model config dict. If None, loads from config/s1_ar_prediction.yml.

    Returns
    -------
    pd.DataFrame : merged feature DataFrame
    """
    if config is None:
        config = _load_default_config()

    logger.info("=" * 60)
    logger.info("S1 INPUT FORMAT - START")
    logger.info("=" * 60)

    # ------------------------------------------------------------------
    # 1. Load feature tables specified in config
    # ------------------------------------------------------------------
    feature_tables_needed = config.get("feature_tables", [
        "invoice_features", "customer_features",
        "collections_features", "customer_payment_scores",
    ])

    logger.info("Loading feature tables: %s", feature_tables_needed)
    loaded = {}
    for table_name in feature_tables_needed:
        path = FEATURE_DIR / f"{table_name}.csv"
        loaded[table_name] = pd.read_csv(path)
        logger.info("  %-30s %s", table_name, loaded[table_name].shape)

    # ------------------------------------------------------------------
    # 2. Merge: invoice_features as base
    # ------------------------------------------------------------------
    merged = loaded["invoice_features"].copy()
    logger.info("Base table: invoice_features %s", merged.shape)

    # Merge customer_features on customer_id
    if "customer_features" in loaded:
        logger.info("Merging customer_features on customer_id")
        # Get feature columns from config
        cust_feature_cols = config.get("features", {}).get("customer_behaviour", [])
        if cust_feature_cols:
            cust_cols_to_use = ["customer_id"] + cust_feature_cols
            # Only keep columns that exist
            available = [
                c for c in cust_cols_to_use
                if c in loaded["customer_features"].columns
            ]
            cust_subset = loaded["customer_features"][available]
        else:
            # Fallback: use all except metadata
            drop_cols = ["feature_date", "feature_version"]
            cust_subset = loaded["customer_features"].drop(
                columns=[c for c in drop_cols if c in loaded["customer_features"].columns]
            )

        merged = merged.merge(cust_subset, on="customer_id", how="left")
        logger.info("  After customer merge: %s", merged.shape)

    # Merge collections_features on invoice_id
    if "collections_features" in loaded:
        logger.info("Merging collections_features on invoice_id")
        merged = merged.merge(
            loaded["collections_features"], on="invoice_id", how="left"
        )
        logger.info("  After collections merge: %s", merged.shape)

    # Merge customer_payment_scores on customer_id
    if "customer_payment_scores" in loaded:
        logger.info("Merging customer_payment_scores on customer_id")
        score_cols_needed = config.get("features", {}).get("customer_scores", [])
        if score_cols_needed:
            score_cols = ["customer_id"] + score_cols_needed
            # Also grab risk_segment for encoding
            if "risk_segment" not in score_cols:
                score_cols.append("risk_segment")
            available = [
                c for c in score_cols
                if c in loaded["customer_payment_scores"].columns
            ]
        else:
            available = [
                "customer_id", "payment_score", "expected_delay", "risk_segment"
            ]
        merged = merged.merge(
            loaded["customer_payment_scores"][available],
            on="customer_id", how="left",
        )
        logger.info("  After scores merge: %s", merged.shape)

    # ------------------------------------------------------------------
    # 3. Derive additional columns
    # ------------------------------------------------------------------
    logger.info("Deriving additional columns")

    # Parse payment_terms to numeric days
    terms_map = {"NET15": 15, "NET30": 30, "NET45": 45, "NET60": 60, "NET90": 90}
    merged["payment_terms_days"] = (
        merged["payment_terms"].map(terms_map).fillna(30).astype(int)
    )

    # Days until promise-to-pay
    merged["promise_to_pay_date"] = pd.to_datetime(
        merged["promise_to_pay_date"], errors="coerce"
    )
    merged["feature_date_dt"] = pd.to_datetime(merged["feature_date"])
    merged["days_until_ptp"] = (
        merged["promise_to_pay_date"] - merged["feature_date_dt"]
    ).dt.days
    merged["days_until_ptp"] = merged["days_until_ptp"].fillna(-1).astype(int)

    merged = merged.drop(columns=["feature_date_dt"], errors="ignore")

    logger.info("  Final merged shape: %s", merged.shape)
    logger.info("  Columns (%d): %s", len(merged.columns), list(merged.columns))

    logger.info("=" * 60)
    logger.info("S1 INPUT FORMAT - COMPLETE")
    logger.info("=" * 60)

    return merged


if __name__ == "__main__":
    df = run()
    print(f"Output shape: {df.shape}")
