"""
S2 AP Payment Prediction - Preprocessing
==========================================
Takes merged input from input_format, derives the target variable
(adjustment_delta), encodes features, and splits into train/test sets.

adjustment_delta = actual_payment_days - rule_based_scheduled_days
  where rule_based_scheduled_days = payment_terms_days (from vendor terms)
  and   actual_payment_days = payment_date - bill_date
"""

import logging
import yaml
import pandas as pd
import numpy as np
from pathlib import Path

logger = logging.getLogger("s2.preprocessing")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DATA_DIR = BASE_DIR / "Data"
CONFIG_PATH = BASE_DIR / "config" / "s2_ap_prediction.yml"


def _load_default_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def _get_feature_columns(config):
    """Flatten all feature groups from config into a single list."""
    features_cfg = config.get("features", {})
    all_features = []
    for group_name, cols in features_cfg.items():
        if isinstance(cols, list):
            all_features.extend(cols)
    return all_features


def run(merged_df, config=None):
    """
    Preprocess merged data for S2 model training.

    Parameters
    ----------
    merged_df : pd.DataFrame
        Output from input_format.run()
    config : dict or None
        Model config.

    Returns
    -------
    dict with keys: X_train, X_test, y_train, y_test, feature_columns
    """
    if config is None:
        config = _load_default_config()

    logger.info("=" * 60)
    logger.info("S2 PREPROCESSING - START")
    logger.info("=" * 60)

    df = merged_df.copy()
    logger.info("Input shape: %s", df.shape)

    # ------------------------------------------------------------------
    # 1. Derive target: adjustment_delta
    # ------------------------------------------------------------------
    target_cfg = config.get("target", {})
    target_col = target_cfg.get("column", "adjustment_delta")
    logger.info("Deriving target variable: %s", target_col)

    derive_cfg = target_cfg.get("derive_from", {})
    payments_file = derive_cfg.get("payments_table", "payments.csv")
    ref_type = derive_cfg.get("reference_type", "AP")

    payments = pd.read_csv(DATA_DIR / payments_file)
    payments["payment_date"] = pd.to_datetime(payments["payment_date"])

    # Get AP payments, take first per bill
    filtered_payments = payments[payments["reference_type"] == ref_type].copy()
    first_payment = (
        filtered_payments.sort_values("payment_date")
        .groupby("reference_id")
        .first()
        .reset_index()
    )

    df["bill_date"] = pd.to_datetime(df["bill_date"])
    df["due_date"] = pd.to_datetime(df["due_date"])

    df = df.merge(
        first_payment[["reference_id", "payment_date"]],
        left_on="bill_id",
        right_on="reference_id",
        how="left",
    )

    # actual_payment_days = payment_date - bill_date
    df["actual_payment_days"] = (df["payment_date"] - df["bill_date"]).dt.days

    # rule_based_scheduled_days = payment_terms_days
    df["rule_based_days"] = df["payment_terms_days"]

    # adjustment_delta = actual - rule_based
    df[target_col] = df["actual_payment_days"] - df["rule_based_days"]

    # Keep only bills with known payment
    paid_count = df[target_col].notna().sum()
    total_count = len(df)
    logger.info(
        "  Bills with payment: %d / %d (%.1f%%)",
        paid_count, total_count, 100 * paid_count / total_count,
    )
    df = df.dropna(subset=[target_col])
    df[target_col] = df[target_col].astype(int)

    # Outlier filter from config
    outlier_cfg = target_cfg.get("outlier_filter", {})
    min_days = outlier_cfg.get("min_days", -60)
    max_days = outlier_cfg.get("max_days", 60)
    before = len(df)
    df = df[(df[target_col] >= min_days) & (df[target_col] <= max_days)]
    logger.info(
        "  Removed %d outlier rows (%s < %d or > %d)",
        before - len(df), target_col, min_days, max_days,
    )

    logger.info(
        "  Target distribution: mean=%.1f, median=%.1f, std=%.1f",
        df[target_col].mean(), df[target_col].median(), df[target_col].std(),
    )

    # ------------------------------------------------------------------
    # 2. Encode categorical features from config
    # ------------------------------------------------------------------
    logger.info("Encoding categorical features")

    encoding_cfg = config.get("encoding", {})

    for col_name, enc_info in encoding_cfg.get("ordinal", {}).items():
        mapping = enc_info.get("mapping", {})
        output_col = enc_info.get("output_col", f"{col_name}_enc")
        if col_name in df.columns:
            df[output_col] = df[col_name].map(mapping).fillna(
                list(mapping.values())[len(mapping) // 2]
            )
            logger.info("  Encoded %-30s -> %s", col_name, output_col)

    for col_name in encoding_cfg.get("boolean_to_int", []):
        if col_name in df.columns:
            df[col_name] = df[col_name].astype(int)
            logger.info("  Bool->Int: %s", col_name)

    # ------------------------------------------------------------------
    # 3. Select feature columns from config
    # ------------------------------------------------------------------
    logger.info("Selecting feature columns from config")

    feature_columns = _get_feature_columns(config)
    available_features = [c for c in feature_columns if c in df.columns]
    missing_features = [c for c in feature_columns if c not in df.columns]

    if missing_features:
        logger.warning("  Missing features (skipped): %s", missing_features)
    logger.info(
        "  Using %d / %d configured features",
        len(available_features), len(feature_columns),
    )

    # ------------------------------------------------------------------
    # 4. Handle NaNs
    # ------------------------------------------------------------------
    X = df[available_features].copy()
    y = df[target_col].copy()

    nan_counts = X.isna().sum()
    cols_with_nan = nan_counts[nan_counts > 0]
    if len(cols_with_nan) > 0:
        logger.info("  Filling NaNs in %d columns:", len(cols_with_nan))
        for col in cols_with_nan.index:
            logger.info("    %-35s %d NaNs", col, cols_with_nan[col])
    X = X.fillna(0)

    # ------------------------------------------------------------------
    # 5. Train / Test split from config
    # ------------------------------------------------------------------
    split_cfg = config.get("split", {})
    test_size = split_cfg.get("test_size", 0.2)
    method = split_cfg.get("method", "time_based")
    sort_col = split_cfg.get("sort_column", "bill_date")

    logger.info("Splitting: method=%s, test_size=%.2f", method, test_size)

    if method == "time_based" and sort_col in df.columns:
        df_sorted = df.sort_values(sort_col).reset_index(drop=True)
    elif method == "random":
        df_sorted = df.sample(frac=1, random_state=42).reset_index(drop=True)
    else:
        df_sorted = df.reset_index(drop=True)

    X = df_sorted[available_features].fillna(0)
    y = df_sorted[target_col]

    split_idx = int(len(df_sorted) * (1 - test_size))
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

    # Preserve metadata for output generation
    meta_cols = ["bill_id", "vendor_id", "bill_date", "due_date", "bill_amount", "payment_terms_days"]
    meta_available = [c for c in meta_cols if c in df_sorted.columns]
    metadata = df_sorted[meta_available].copy()
    meta_train = metadata.iloc[:split_idx].reset_index(drop=True)
    meta_test = metadata.iloc[split_idx:].reset_index(drop=True)

    all_meta = df[meta_available].copy() if len(meta_available) > 0 else pd.DataFrame()
    all_X = df[available_features].fillna(0)

    logger.info("  Train: %d samples", len(X_train))
    logger.info("  Test:  %d samples", len(X_test))
    logger.info(
        "  Target stats (train) - mean: %.1f, median: %.1f, std: %.1f",
        y_train.mean(), y_train.median(), y_train.std(),
    )
    logger.info(
        "  Target stats (test)  - mean: %.1f, median: %.1f, std: %.1f",
        y_test.mean(), y_test.median(), y_test.std(),
    )

    logger.info("=" * 60)
    logger.info("S2 PREPROCESSING - COMPLETE")
    logger.info("=" * 60)

    return {
        "X_train": X_train,
        "X_test": X_test,
        "y_train": y_train,
        "y_test": y_test,
        "feature_columns": available_features,
        "meta_train": meta_train,
        "meta_test": meta_test,
        "all_meta": all_meta,
        "all_X": all_X,
    }


if __name__ == "__main__":
    from steps.s2_ap_prediction.input_format import run as input_format_run

    merged = input_format_run()
    result = run(merged)
    print(f"Train shape: {result['X_train'].shape}")
    print(f"Test shape:  {result['X_test'].shape}")
