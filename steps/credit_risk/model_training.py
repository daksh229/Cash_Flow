"""
Credit Risk Assessment - Model Training
==========================================
Trains LightGBM (primary) and Random Forest (baseline) classifiers
to predict risk_segment (LOW / MEDIUM / HIGH).

Handles class imbalance via class weights. Tracks with MLflow.
"""

import os
import logging
import yaml
import joblib
import numpy as np
import mlflow
import mlflow.sklearn
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.model_selection import cross_val_score
from sklearn.utils.class_weight import compute_class_weight

try:
    import lightgbm as lgb
    HAS_LIGHTGBM = True
except ImportError:
    HAS_LIGHTGBM = False

logger = logging.getLogger("credit_risk.model_training")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / "config" / "credit_risk.yml"


def _load_default_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def _compute_sample_weights(y_train):
    """Compute sample weights for class imbalance."""
    classes = np.unique(y_train)
    weights = compute_class_weight("balanced", classes=classes, y=y_train)
    weight_map = dict(zip(classes, weights))
    return np.array([weight_map[v] for v in y_train])


def run(preprocessed_data, config=None, master_cfg=None):
    """
    Train classification models and log to MLflow.

    Parameters
    ----------
    preprocessed_data : dict
        Output from preprocessing.run()
    config : dict or None
    master_cfg : dict or None

    Returns
    -------
    dict with trained models, predictions, and data
    """
    if config is None:
        config = _load_default_config()
    if master_cfg is None:
        master_cfg = {}

    logger.info("=" * 60)
    logger.info("CREDIT RISK MODEL TRAINING - START")
    logger.info("=" * 60)

    X_train = preprocessed_data["X_train"]
    X_test = preprocessed_data["X_test"]
    y_train = preprocessed_data["y_train"]
    y_test = preprocessed_data["y_test"]
    feature_columns = preprocessed_data["feature_columns"]
    class_names = preprocessed_data["class_names"]

    logger.info("Train samples: %d | Test samples: %d", len(X_train), len(X_test))
    logger.info("Features: %d | Classes: %s", len(feature_columns), class_names)

    # Model directory
    global_cfg = master_cfg.get("global", {})
    model_dir = BASE_DIR / global_cfg.get("model_dir", "models") / "credit_risk"
    os.makedirs(model_dir, exist_ok=True)

    # ------------------------------------------------------------------
    # Class imbalance handling
    # ------------------------------------------------------------------
    imbalance_cfg = config.get("class_imbalance", {})
    imbalance_method = imbalance_cfg.get("method", "class_weight")
    sample_weights = None

    if imbalance_method == "class_weight":
        sample_weights = _compute_sample_weights(y_train.values)
        logger.info("Class imbalance: using computed sample weights")
    else:
        logger.info("Class imbalance: method=%s", imbalance_method)

    # ------------------------------------------------------------------
    # MLflow setup
    # ------------------------------------------------------------------
    mlflow_cfg = master_cfg.get("mlflow", {})
    if mlflow_cfg.get("enabled", True):
        tracking_path = BASE_DIR / mlflow_cfg.get("tracking_uri", "mlruns")
        tracking_uri = tracking_path.as_uri()
        experiment_prefix = mlflow_cfg.get("experiment_prefix", "CashFlow")
        experiment_name = f"{experiment_prefix}_Credit_Risk"

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

    # Hyperparameters
    primary_cfg = config.get("primary_model", {})
    baseline_cfg = config.get("baseline_model", {})
    primary_params = primary_cfg.get("hyperparameters", {})
    baseline_params = baseline_cfg.get("hyperparameters", {})

    run_context = (
        mlflow.start_run(run_name="credit_risk_training")
        if mlflow_enabled
        else _nullcontext()
    )

    with run_context as ml_run:
        if mlflow_enabled:
            mlflow.set_tag("model_type", "classification")
            mlflow.set_tag("target", "risk_segment")
            mlflow.set_tag("module", "Credit_Risk")
            mlflow.log_param("train_samples", len(X_train))
            mlflow.log_param("test_samples", len(X_test))
            mlflow.log_param("num_features", len(feature_columns))
            mlflow.log_param("num_classes", len(class_names))
            mlflow.log_param("imbalance_method", imbalance_method)

        # ==============================================================
        # Primary Model: LightGBM Classifier
        # ==============================================================
        lgbm_model = None
        lgbm_pred_train = None
        lgbm_pred_test = None
        lgbm_proba_test = None

        if HAS_LIGHTGBM and primary_cfg.get("type") == "lightgbm":
            logger.info("Training LightGBM Classifier (primary model)")
            logger.info("  Hyperparameters: %s", primary_params)

            lgbm_params = {
                **primary_params,
                "random_state": 42,
                "n_jobs": -1,
                "is_unbalance": True,
            }
            lgbm_model = lgb.LGBMClassifier(**lgbm_params)
            lgbm_model.fit(
                X_train, y_train,
                sample_weight=sample_weights,
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

            # Cross-validation
            if cv_enabled:
                cv_model = lgb.LGBMClassifier(**lgbm_params)
                cv_scores = cross_val_score(
                    cv_model, X_train, y_train,
                    cv=cv_folds, scoring="f1_macro", n_jobs=-1,
                )
                logger.info(
                    "  LightGBM CV F1-macro: %.4f (+/- %.4f)",
                    cv_scores.mean(), cv_scores.std(),
                )
                if mlflow_enabled:
                    mlflow.log_metric("lgbm_cv_f1_macro_mean", cv_scores.mean())
                    mlflow.log_metric("lgbm_cv_f1_macro_std", cv_scores.std())

            lgbm_pred_train = lgbm_model.predict(X_train)
            lgbm_pred_test = lgbm_model.predict(X_test)
            lgbm_proba_test = lgbm_model.predict_proba(X_test)

            # Save
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
        # Baseline Model: Random Forest Classifier
        # ==============================================================
        logger.info("Training Random Forest Classifier (baseline model)")
        logger.info("  Hyperparameters: %s", baseline_params)

        rf_params = {**baseline_params, "random_state": 42, "n_jobs": -1}
        rf_model = RandomForestClassifier(**rf_params)
        rf_model.fit(X_train, y_train, sample_weight=sample_weights)

        importance_rf = sorted(
            zip(X_train.columns, rf_model.feature_importances_),
            key=lambda x: x[1], reverse=True,
        )
        logger.info("  Top 10 features (RF):")
        for feat, imp in importance_rf[:10]:
            logger.info("    %-35s %.4f", feat, imp)

        if cv_enabled:
            cv_rf = RandomForestClassifier(**rf_params)
            cv_scores_rf = cross_val_score(
                cv_rf, X_train, y_train,
                cv=cv_folds, scoring="f1_macro", n_jobs=-1,
            )
            logger.info(
                "  RF CV F1-macro: %.4f (+/- %.4f)",
                cv_scores_rf.mean(), cv_scores_rf.std(),
            )
            if mlflow_enabled:
                mlflow.log_metric("rf_cv_f1_macro_mean", cv_scores_rf.mean())
                mlflow.log_metric("rf_cv_f1_macro_std", cv_scores_rf.std())

        rf_pred_train = rf_model.predict(X_train)
        rf_pred_test = rf_model.predict(X_test)
        rf_proba_test = rf_model.predict_proba(X_test)

        rf_path = model_dir / "rf_model.pkl"
        joblib.dump(rf_model, rf_path)
        logger.info("  RF model saved to %s", rf_path)

        if mlflow_enabled:
            for k, v in baseline_params.items():
                mlflow.log_param(f"rf_{k}", v)
            mlflow.sklearn.log_model(rf_model, "rf_model")

        # Model agreement
        if lgbm_pred_test is not None:
            agreement = (lgbm_pred_test == rf_pred_test).mean()
            logger.info("  Model agreement (test): %.1f%%", 100 * agreement)
            if mlflow_enabled:
                mlflow.log_metric("model_agreement", round(100 * agreement, 1))

        if mlflow_enabled:
            logger.info("  MLflow run ID: %s", ml_run.info.run_id)

    logger.info("=" * 60)
    logger.info("CREDIT RISK MODEL TRAINING - COMPLETE")
    logger.info("=" * 60)

    return {
        "lgbm_model": lgbm_model,
        "rf_model": rf_model,
        "predictions": {
            "lgbm_train": lgbm_pred_train,
            "lgbm_test": lgbm_pred_test,
            "lgbm_proba_test": lgbm_proba_test,
            "rf_train": rf_pred_train,
            "rf_test": rf_pred_test,
            "rf_proba_test": rf_proba_test,
        },
        "X_train": X_train,
        "X_test": X_test,
        "y_train": y_train,
        "y_test": y_test,
        "feature_columns": feature_columns,
        "class_names": class_names,
    }


class _nullcontext:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass


if __name__ == "__main__":
    from steps.credit_risk.input_format import run as input_run
    from steps.credit_risk.preprocessing import run as preprocess_run

    merged = input_run()
    preprocessed = preprocess_run(merged)
    result = run(preprocessed)
