"""
S2 AP Payment Prediction - Input Format
=========================================
Loads vendor_features and bill_features, merges them into a single
DataFrame ready for preprocessing.

Reads configuration from model config (passed by main.py or used standalone).
"""

import logging
import yaml
import pandas as pd
from pathlib import Path

logger = logging.getLogger("s2.input_format")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
FEATURE_DIR = BASE_DIR / "Data" / "features"
CONFIG_PATH = BASE_DIR / "config" / "s2_ap_prediction.yml"


def _load_default_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def run(config=None):
    """
    Load and merge feature tables for S2 AP prediction.

    Parameters
    ----------
    config : dict or None
        Model config dict. If None, loads from config/s2_ap_prediction.yml.

    Returns
    -------
    pd.DataFrame : merged feature DataFrame
    """
    if config is None:
        config = _load_default_config()

    logger.info("=" * 60)
    logger.info("S2 INPUT FORMAT - START")
    logger.info("=" * 60)

    # ------------------------------------------------------------------
    # 1. Load feature tables specified in config
    # ------------------------------------------------------------------
    feature_tables_needed = config.get("feature_tables", [
        "vendor_features", "bill_features",
    ])

    logger.info("Loading feature tables: %s", feature_tables_needed)
    loaded = {}
    for table_name in feature_tables_needed:
        path = FEATURE_DIR / f"{table_name}.csv"
        loaded[table_name] = pd.read_csv(path)
        logger.info("  %-30s %s", table_name, loaded[table_name].shape)

    # ------------------------------------------------------------------
    # 2. Merge: bill_features as base, join vendor_features
    # ------------------------------------------------------------------
    merged = loaded["bill_features"].copy()
    logger.info("Base table: bill_features %s", merged.shape)

    if "vendor_features" in loaded:
        logger.info("Merging vendor_features on vendor_id")

        # Get vendor behaviour columns from config
        vend_feature_cols = config.get("features", {}).get("vendor_behaviour", [])
        if vend_feature_cols:
            vend_cols_to_use = ["vendor_id"] + vend_feature_cols
            available = [
                c for c in vend_cols_to_use
                if c in loaded["vendor_features"].columns
            ]
            vend_subset = loaded["vendor_features"][available]
        else:
            drop_cols = ["feature_date", "feature_version", "last_payment_date"]
            vend_subset = loaded["vendor_features"].drop(
                columns=[c for c in drop_cols if c in loaded["vendor_features"].columns]
            )

        merged = merged.merge(vend_subset, on="vendor_id", how="left")
        logger.info("  After vendor merge: %s", merged.shape)

    # ------------------------------------------------------------------
    # 3. Add vendor payment terms from raw vendors table
    # ------------------------------------------------------------------
    logger.info("Adding vendor payment_terms from raw data")
    vendors = pd.read_csv(BASE_DIR / "Data" / "vendors.csv")
    vendors["payment_terms"] = vendors["payment_terms"]

    # Parse payment terms to numeric days
    terms_map = {"NET15": 15, "NET30": 30, "NET45": 45, "NET60": 60, "NET90": 90}
    vendors["payment_terms_days"] = (
        vendors["payment_terms"].map(terms_map).fillna(30).astype(int)
    )
    merged = merged.merge(
        vendors[["vendor_id", "payment_terms_days"]], on="vendor_id", how="left"
    )
    merged["payment_terms_days"] = merged["payment_terms_days"].fillna(30).astype(int)

    # ------------------------------------------------------------------
    # 4. Add bill_date from raw bills table (needed for target derivation)
    # ------------------------------------------------------------------
    bills = pd.read_csv(BASE_DIR / "Data" / "bills.csv")
    merged = merged.merge(
        bills[["bill_id", "bill_date", "due_date", "bill_status"]],
        on="bill_id", how="left",
    )

    logger.info("  Final merged shape: %s", merged.shape)
    logger.info("  Columns (%d): %s", len(merged.columns), list(merged.columns))

    logger.info("=" * 60)
    logger.info("S2 INPUT FORMAT - COMPLETE")
    logger.info("=" * 60)

    return merged


if __name__ == "__main__":
    df = run()
    print(f"Output shape: {df.shape}")
