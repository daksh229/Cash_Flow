"""
Credit Risk Assessment - Preprocessing
=========================================
Takes merged input from input_format, encodes the target variable
(risk_segment -> 0/1/2), selects features, handles class imbalance,
and splits into train/test sets.
"""

import logging
import yaml
import pandas as pd
import numpy as np
from pathlib import Path
from sklearn.model_selection import train_test_split

logger = logging.getLogger("credit_risk.preprocessing")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / "config" / "credit_risk.yml"


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
    Preprocess data for Credit Risk classification.

    Parameters
    ----------
    merged_df : pd.DataFrame
        Output from input_format.run()
    config : dict or None

    Returns
    -------
    dict with keys: X_train, X_test, y_train, y_test, feature_columns, class_names
    """
    if config is None:
        config = _load_default_config()

    logger.info("=" * 60)
    logger.info("CREDIT RISK PREPROCESSING - START")
    logger.info("=" * 60)

    df = merged_df.copy()
    logger.info("Input shape: %s", df.shape)

    # ------------------------------------------------------------------
    # 1. Encode target variable
    # ------------------------------------------------------------------
    target_cfg = config.get("target", {})
    target_col = target_cfg.get("column", "risk_segment")
    class_encoding = target_cfg.get("class_encoding", {"LOW": 0, "MEDIUM": 1, "HIGH": 2})
    class_names = target_cfg.get("classes", ["LOW", "MEDIUM", "HIGH"])

    logger.info("Encoding target: %s", target_col)
    logger.info("  Class encoding: %s", class_encoding)

    # Drop rows with missing target
    before = len(df)
    df = df.dropna(subset=[target_col])
    if before - len(df) > 0:
        logger.info("  Dropped %d rows with missing target", before - len(df))

    df["target"] = df[target_col].map(class_encoding)

    logger.info("  Class distribution:")
    for cls_name, cls_val in class_encoding.items():
        count = (df["target"] == cls_val).sum()
        pct = 100 * count / len(df)
        logger.info("    %-10s (=%d): %5d samples (%5.1f%%)", cls_name, cls_val, count, pct)

    # ------------------------------------------------------------------
    # 2. Select feature columns from config
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
    # 3. Encode categoricals from config (if any)
    # ------------------------------------------------------------------
    encoding_cfg = config.get("encoding", {})

    for col_name, enc_info in encoding_cfg.get("ordinal", {}).items():
        mapping = enc_info.get("mapping", {})
        output_col = enc_info.get("output_col", f"{col_name}_enc")
        if col_name in df.columns:
            df[output_col] = df[col_name].map(mapping).fillna(0)
            logger.info("  Encoded %-30s -> %s", col_name, output_col)

    for col_name in encoding_cfg.get("boolean_to_int", []):
        if col_name in df.columns:
            df[col_name] = df[col_name].astype(int)

    # ------------------------------------------------------------------
    # 4. Handle NaNs
    # ------------------------------------------------------------------
    X = df[available_features].copy()
    y = df["target"].copy()

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
    method = split_cfg.get("method", "stratified")

    logger.info("Splitting: method=%s, test_size=%.2f", method, test_size)

    if method == "stratified":
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42, stratify=y,
        )
    elif method == "random":
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42,
        )
    else:
        split_idx = int(len(X) * (1 - test_size))
        X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
        y_train, y_test = y.iloc[:split_idx], y.iloc[split_idx:]

    logger.info("  Train: %d samples", len(X_train))
    logger.info("  Test:  %d samples", len(X_test))

    logger.info("  Train class distribution:")
    for cls_name, cls_val in class_encoding.items():
        count = (y_train == cls_val).sum()
        logger.info("    %-10s %d (%.1f%%)", cls_name, count, 100 * count / len(y_train))

    logger.info("  Test class distribution:")
    for cls_name, cls_val in class_encoding.items():
        count = (y_test == cls_val).sum()
        logger.info("    %-10s %d (%.1f%%)", cls_name, count, 100 * count / len(y_test))

    logger.info("=" * 60)
    logger.info("CREDIT RISK PREPROCESSING - COMPLETE")
    logger.info("=" * 60)

    return {
        "X_train": X_train,
        "X_test": X_test,
        "y_train": y_train,
        "y_test": y_test,
        "feature_columns": available_features,
        "class_names": class_names,
        "class_encoding": class_encoding,
    }


if __name__ == "__main__":
    from steps.credit_risk.input_format import run as input_format_run

    merged = input_format_run()
    result = run(merged)
    print(f"Train shape: {result['X_train'].shape}")
    print(f"Test shape:  {result['X_test'].shape}")
