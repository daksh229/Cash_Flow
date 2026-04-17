"""
S2 AP Payment Prediction - Model Training
============================================
Trains LightGBM (primary) and Random Forest (baseline) regressors
to predict adjustment_delta for vendor bill payments.

All hyperparameters are read from config. Tracks experiments with MLflow.
"""

import os
import logging
import yaml
import joblib
import numpy as np
import pandas as pd
import mlflow
import mlflow.sklearn
from pathlib import Path
from sklearn.ensemble import RandomForestRegressor
from sklearn.model_selection import cross_val_score

try:
    import lightgbm as lgb
    HAS_LIGHTGBM = True
except ImportError:
    HAS_LIGHTGBM = False

logger = logging.getLogger("s2.model_training")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / "config" / "s2_ap_prediction.yml"


def _load_default_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def _build_lgbm_model(params):
    model_params = {**params, "random_state": 42, "n_jobs": -1}
    return lgb.LGBMRegressor(**model_params)


def _build_rf_model(params):
    model_params = {**params, "random_state": 42, "n_jobs": -1}
    return RandomForestRegressor(**model_params)


def run(preprocessed_data, config=None, master_cfg=None):
    """
    Train both models and log to MLflow.

    Parameters
    ----------
    preprocessed_data : dict
        Output from preprocessing.run()
    config : dict or None
        Model config.
    master_cfg : dict or None
        Master config for global settings.

    Returns
    -------
    dict with trained models, predictions, and data
    """
    if config is None:
        config = _load_default_config()
    if master_cfg is None:
        master_cfg = {}

    logger.info("=" * 60)
    logger.info("S2 MODEL TRAINING - START")
    logger.info("=" * 60)

    X_train = preprocessed_data["X_train"]
    X_test = preprocessed_data["X_test"]
    y_train = preprocessed_data["y_train"]
    y_test = preprocessed_data["y_test"]
    feature_columns = preprocessed_data["feature_columns"]

    logger.info("Train samples: %d | Test samples: %d", len(X_train), len(X_test))
    logger.info("Features: %d", len(feature_columns))

    # Model directory
    global_cfg = master_cfg.get("global", {})
    model_dir = BASE_DIR / global_cfg.get("model_dir", "models") / "s2_ap_prediction"
    os.makedirs(model_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # MLflow setup
    # ------------------------------------------------------------------
    mlflow_cfg = master_cfg.get("mlflow", {})
    if mlflow_cfg.get("enabled", True):
        tracking_path = BASE_DIR / mlflow_cfg.get("tracking_uri", "mlruns")
        tracking_uri = tracking_path.as_uri()
        experiment_prefix = mlflow_cfg.get("experiment_prefix", "CashFlow")
        experiment_name = f"{experiment_prefix}_S2_AP_Prediction"

        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(experiment_name)
        mlflow_enabled = True
    else:
        mlflow_enabled = False

    # CV settings
    training_cfg = master_cfg.get("training", {})
    cv_cfg = training_cfg.get("cross_validation", {})
    cv_enabled = cv_cfg.get("enabled", True)
    cv_folds = cv_cfg.get("folds", 5)
    cv_scoring = cv_cfg.get("scoring", "neg_mean_absolute_error")

    # Hyperparameters from config
    primary_cfg = config.get("primary_model", {})
    baseline_cfg = config.get("baseline_model", {})
    primary_params = primary_cfg.get("hyperparameters", {})
    baseline_params = baseline_cfg.get("hyperparameters", {})

    run_context = (
        mlflow.start_run(run_name="s2_training")
        if mlflow_enabled
        else _nullcontext()
    )

    with run_context as ml_run:
        if mlflow_enabled:
            mlflow.set_tag("model_type", "regression")
            mlflow.set_tag("target", config["model_info"]["target"])
            mlflow.set_tag("module", "S2_AP_Payment")
            mlflow.log_param("train_samples", len(X_train))
            mlflow.log_param("test_samples", len(X_test))
            mlflow.log_param("num_features", len(feature_columns))

        # ==============================================================
        # Primary Model: LightGBM
        # ==============================================================
        lgbm_model = None
        lgbm_pred_train = None
        lgbm_pred_test = None

        if HAS_LIGHTGBM and primary_cfg.get("type") == "lightgbm":
            logger.info("Training LightGBM (primary model)")
            logger.info("  Hyperparameters: %s", primary_params)

            lgbm_model = _build_lgbm_model(primary_params)
            lgbm_model.fit(
                X_train, y_train,
                eval_set=[(X_test, y_test)],
                callbacks=[lgb.log_evaluation(period=100)],
            )

            # Feature importance
            importance = sorted(
                zip(X_train.columns, lgbm_model.feature_importances_),
                key=lambda x: x[1], reverse=True,
            )
            logger.info("  Top 10 features (LightGBM):")
            for feat, imp in importance[:10]:
                logger.info("    %-35s %d", feat, imp)

            if cv_enabled:
                cv_model = _build_lgbm_model(primary_params)
                cv_scores = cross_val_score(
                    cv_model, X_train, y_train,
                    cv=cv_folds, scoring=cv_scoring, n_jobs=-1,
                )
                logger.info(
                    "  LightGBM CV MAE: %.2f (+/- %.2f)",
                    -cv_scores.mean(), cv_scores.std(),
                )
                if mlflow_enabled:
                    mlflow.log_metric("lgbm_cv_mae_mean", -cv_scores.mean())
                    mlflow.log_metric("lgbm_cv_mae_std", cv_scores.std())

            lgbm_pred_train = lgbm_model.predict(X_train)
            lgbm_pred_test = lgbm_model.predict(X_test)

            lgbm_path = model_dir / "lgbm_model.pkl"
            joblib.dump(lgbm_model, lgbm_path)
            logger.info("  LightGBM model saved to %s", lgbm_path)

            if mlflow_enabled:
                for k, v in primary_params.items():
                    mlflow.log_param(f"lgbm_{k}", v)
                mlflow.sklearn.log_model(lgbm_model, "lgbm_model")
        else:
            if not HAS_LIGHTGBM:
                logger.warning("LightGBM not installed, skipping primary model")

        # ==============================================================
        # Baseline Model: Random Forest
        # ==============================================================
        logger.info("Training Random Forest (baseline model)")
        logger.info("  Hyperparameters: %s", baseline_params)

        rf_model = _build_rf_model(baseline_params)
        rf_model.fit(X_train, y_train)

        importance_rf = sorted(
            zip(X_train.columns, rf_model.feature_importances_),
            key=lambda x: x[1], reverse=True,
        )
        logger.info("  Top 10 features (RF):")
        for feat, imp in importance_rf[:10]:
            logger.info("    %-35s %.4f", feat, imp)

        if cv_enabled:
            cv_rf = _build_rf_model(baseline_params)
            cv_scores_rf = cross_val_score(
                cv_rf, X_train, y_train,
                cv=cv_folds, scoring=cv_scoring, n_jobs=-1,
            )
            logger.info(
                "  RF CV MAE: %.2f (+/- %.2f)",
                -cv_scores_rf.mean(), cv_scores_rf.std(),
            )
            if mlflow_enabled:
                mlflow.log_metric("rf_cv_mae_mean", -cv_scores_rf.mean())
                mlflow.log_metric("rf_cv_mae_std", cv_scores_rf.std())

        rf_pred_train = rf_model.predict(X_train)
        rf_pred_test = rf_model.predict(X_test)

        rf_path = model_dir / "rf_model.pkl"
        joblib.dump(rf_model, rf_path)
        logger.info("  RF model saved to %s", rf_path)

        if mlflow_enabled:
            for k, v in baseline_params.items():
                mlflow.log_param(f"rf_{k}", v)
            mlflow.sklearn.log_model(rf_model, "rf_model")

        # Model divergence
        if lgbm_pred_test is not None:
            divergence = np.abs(lgbm_pred_test - rf_pred_test)
            logger.info("  Mean model divergence (test): %.2f days", divergence.mean())
            if mlflow_enabled:
                mlflow.log_metric("mean_model_divergence", float(divergence.mean()))

        # Thin-data analysis from config
        thin_threshold = config.get("evaluation", {}).get("thin_data_threshold", 10)
        if "invoice_count" in X_test.columns:
            thin_mask = X_test["invoice_count"] < thin_threshold
            if thin_mask.any() and lgbm_pred_test is not None:
                thin_mae = np.mean(np.abs(
                    y_test.values[thin_mask] - lgbm_pred_test[thin_mask]
                ))
                rich_mae = np.mean(np.abs(
                    y_test.values[~thin_mask] - lgbm_pred_test[~thin_mask]
                )) if (~thin_mask).any() else 0
                logger.info(
                    "  Thin-data vendors (<%d invoices): MAE=%.2f (%d vendors)",
                    thin_threshold, thin_mae, thin_mask.sum(),
                )
                logger.info(
                    "  Rich-data vendors (>=%d invoices): MAE=%.2f (%d vendors)",
                    thin_threshold, rich_mae, (~thin_mask).sum(),
                )
                if mlflow_enabled:
                    mlflow.log_metric("thin_data_mae", thin_mae)
                    mlflow.log_metric("rich_data_mae", rich_mae)

        if mlflow_enabled:
            logger.info("  MLflow run ID: %s", ml_run.info.run_id)

    logger.info("=" * 60)
    logger.info("S2 MODEL TRAINING - COMPLETE")
    logger.info("=" * 60)

    # Generate predictions on ALL data for output tables
    all_X = preprocessed_data.get("all_X")
    all_meta = preprocessed_data.get("all_meta", pd.DataFrame())
    lgbm_pred_all = lgbm_model.predict(all_X) if lgbm_model is not None and all_X is not None else None
    rf_pred_all = rf_model.predict(all_X) if all_X is not None else None

    return {
        "lgbm_model": lgbm_model,
        "rf_model": rf_model,
        "predictions": {
            "lgbm_train": lgbm_pred_train,
            "lgbm_test": lgbm_pred_test,
            "rf_train": rf_pred_train,
            "rf_test": rf_pred_test,
            "lgbm_all": lgbm_pred_all,
            "rf_all": rf_pred_all,
        },
        "X_train": X_train,
        "X_test": X_test,
        "y_train": y_train,
        "y_test": y_test,
        "feature_columns": feature_columns,
        "all_meta": all_meta,
    }


class _nullcontext:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass


if __name__ == "__main__":
    from steps.s2_ap_prediction.input_format import run as input_run
    from steps.s2_ap_prediction.preprocessing import run as preprocess_run

    merged = input_run()
    preprocessed = preprocess_run(merged)
    result = run(preprocessed)
