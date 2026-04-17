"""
Credit Risk Assessment - Evaluation
======================================
Evaluates classification models with:
  - Accuracy, Precision, Recall, F1 (macro + per-class)
  - Confusion Matrix
  - AUC-ROC (one-vs-rest)
  - Per-class detailed report
"""

import os
import logging
import yaml
import numpy as np
import pandas as pd
import mlflow
from pathlib import Path
from sklearn.metrics import (
    accuracy_score,
    precision_score,
    recall_score,
    f1_score,
    confusion_matrix,
    classification_report,
    roc_auc_score,
)

logger = logging.getLogger("credit_risk.evaluate")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / "config" / "credit_risk.yml"


def _load_default_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def _compute_classification_metrics(y_true, y_pred, y_proba, class_names):
    """Compute classification metrics."""
    metrics = {}

    metrics["accuracy"] = round(accuracy_score(y_true, y_pred), 4)
    metrics["precision_macro"] = round(
        precision_score(y_true, y_pred, average="macro", zero_division=0), 4
    )
    metrics["recall_macro"] = round(
        recall_score(y_true, y_pred, average="macro", zero_division=0), 4
    )
    metrics["f1_macro"] = round(
        f1_score(y_true, y_pred, average="macro", zero_division=0), 4
    )
    metrics["precision_weighted"] = round(
        precision_score(y_true, y_pred, average="weighted", zero_division=0), 4
    )
    metrics["recall_weighted"] = round(
        recall_score(y_true, y_pred, average="weighted", zero_division=0), 4
    )
    metrics["f1_weighted"] = round(
        f1_score(y_true, y_pred, average="weighted", zero_division=0), 4
    )

    # Per-class F1
    per_class_f1 = f1_score(y_true, y_pred, average=None, zero_division=0)
    for i, cls_name in enumerate(class_names):
        if i < len(per_class_f1):
            metrics[f"f1_{cls_name}"] = round(per_class_f1[i], 4)

    # AUC-ROC (one-vs-rest) — only if probabilities are available
    if y_proba is not None and len(class_names) > 2:
        try:
            auc = roc_auc_score(y_true, y_proba, multi_class="ovr", average="macro")
            metrics["auc_roc_ovr"] = round(auc, 4)
        except ValueError:
            metrics["auc_roc_ovr"] = 0.0

    return metrics


def run(training_result, config=None, master_cfg=None):
    """
    Evaluate classification models and log results.

    Parameters
    ----------
    training_result : dict
        Output from model_training.run()
    config : dict or None
    master_cfg : dict or None

    Returns
    -------
    dict with all evaluation metrics
    """
    if config is None:
        config = _load_default_config()
    if master_cfg is None:
        master_cfg = {}

    logger.info("=" * 60)
    logger.info("CREDIT RISK EVALUATION - START")
    logger.info("=" * 60)

    eval_cfg = config.get("evaluation", {})
    show_confusion = eval_cfg.get("confusion_matrix", True)
    show_per_class = eval_cfg.get("per_class_report", True)

    global_cfg = master_cfg.get("global", {})
    report_dir = BASE_DIR / global_cfg.get("report_dir", "reports") / "credit_risk"
    os.makedirs(report_dir, exist_ok=True)

    y_train = training_result["y_train"].values
    y_test = training_result["y_test"].values
    preds = training_result["predictions"]
    class_names = training_result["class_names"]

    all_metrics = {}

    # ------------------------------------------------------------------
    # MLflow setup
    # ------------------------------------------------------------------
    mlflow_cfg = master_cfg.get("mlflow", {})
    mlflow_enabled = mlflow_cfg.get("enabled", True)

    if mlflow_enabled:
        tracking_path = BASE_DIR / mlflow_cfg.get("tracking_uri", "mlruns")
        tracking_uri = tracking_path.as_uri()
        experiment_prefix = mlflow_cfg.get("experiment_prefix", "CashFlow")
        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(f"{experiment_prefix}_Credit_Risk")

    run_context = (
        mlflow.start_run(run_name="credit_risk_evaluation")
        if mlflow_enabled
        else _nullcontext()
    )

    with run_context as ml_run:
        if mlflow_enabled:
            mlflow.set_tag("stage", "evaluation")

        # ==============================================================
        # LightGBM evaluation
        # ==============================================================
        if preds["lgbm_test"] is not None:
            logger.info("--- LightGBM Evaluation ---")

            # Train
            lgbm_train_m = _compute_classification_metrics(
                y_train, preds["lgbm_train"], None, class_names
            )
            prefixed_train = {f"lgbm_train_{k}": v for k, v in lgbm_train_m.items()}
            all_metrics.update(prefixed_train)
            logger.info("  LightGBM - TRAIN:")
            logger.info("    Accuracy:         %.4f", lgbm_train_m["accuracy"])
            logger.info("    F1 (macro):       %.4f", lgbm_train_m["f1_macro"])

            # Test
            lgbm_test_m = _compute_classification_metrics(
                y_test, preds["lgbm_test"], preds["lgbm_proba_test"], class_names
            )
            prefixed_test = {f"lgbm_test_{k}": v for k, v in lgbm_test_m.items()}
            all_metrics.update(prefixed_test)
            logger.info("  LightGBM - TEST:")
            logger.info("    Accuracy:         %.4f", lgbm_test_m["accuracy"])
            logger.info("    Precision (macro):%.4f", lgbm_test_m["precision_macro"])
            logger.info("    Recall (macro):   %.4f", lgbm_test_m["recall_macro"])
            logger.info("    F1 (macro):       %.4f", lgbm_test_m["f1_macro"])
            logger.info("    F1 (weighted):    %.4f", lgbm_test_m["f1_weighted"])
            if "auc_roc_ovr" in lgbm_test_m:
                logger.info("    AUC-ROC (OVR):    %.4f", lgbm_test_m["auc_roc_ovr"])

            # Per-class F1
            for cls_name in class_names:
                key = f"f1_{cls_name}"
                if key in lgbm_test_m:
                    logger.info("    F1 %-10s:     %.4f", cls_name, lgbm_test_m[key])

            if mlflow_enabled:
                for k, v in {**prefixed_train, **prefixed_test}.items():
                    mlflow.log_metric(k, v)

            # Confusion matrix
            if show_confusion:
                logger.info("  Confusion Matrix (LightGBM - TEST):")
                cm = confusion_matrix(y_test, preds["lgbm_test"])
                logger.info("    Predicted ->  %s", "  ".join(f"{c:>7s}" for c in class_names))
                for i, cls_name in enumerate(class_names):
                    if i < len(cm):
                        row = "  ".join(f"{v:>7d}" for v in cm[i])
                        logger.info("    %-10s    %s", cls_name, row)

                # Save confusion matrix
                cm_df = pd.DataFrame(
                    cm,
                    index=[f"actual_{c}" for c in class_names[:len(cm)]],
                    columns=[f"pred_{c}" for c in class_names[:len(cm[0])]],
                )
                cm_path = report_dir / "confusion_matrix.csv"
                cm_df.to_csv(cm_path)

            # Full classification report
            if show_per_class:
                logger.info("  Classification Report (LightGBM - TEST):")
                report = classification_report(
                    y_test, preds["lgbm_test"],
                    target_names=class_names,
                    zero_division=0,
                )
                for line in report.split("\n"):
                    if line.strip():
                        logger.info("    %s", line)

                report_path = report_dir / "classification_report.txt"
                with open(report_path, "w") as f:
                    f.write(report)

        # ==============================================================
        # Random Forest evaluation
        # ==============================================================
        logger.info("--- Random Forest Evaluation ---")

        rf_train_m = _compute_classification_metrics(
            y_train, preds["rf_train"], None, class_names
        )
        prefixed_train = {f"rf_train_{k}": v for k, v in rf_train_m.items()}
        all_metrics.update(prefixed_train)
        logger.info("  Random Forest - TRAIN:")
        logger.info("    Accuracy:         %.4f", rf_train_m["accuracy"])
        logger.info("    F1 (macro):       %.4f", rf_train_m["f1_macro"])

        rf_test_m = _compute_classification_metrics(
            y_test, preds["rf_test"], preds["rf_proba_test"], class_names
        )
        prefixed_test = {f"rf_test_{k}": v for k, v in rf_test_m.items()}
        all_metrics.update(prefixed_test)
        logger.info("  Random Forest - TEST:")
        logger.info("    Accuracy:         %.4f", rf_test_m["accuracy"])
        logger.info("    Precision (macro):%.4f", rf_test_m["precision_macro"])
        logger.info("    Recall (macro):   %.4f", rf_test_m["recall_macro"])
        logger.info("    F1 (macro):       %.4f", rf_test_m["f1_macro"])
        logger.info("    F1 (weighted):    %.4f", rf_test_m["f1_weighted"])
        if "auc_roc_ovr" in rf_test_m:
            logger.info("    AUC-ROC (OVR):    %.4f", rf_test_m["auc_roc_ovr"])

        if mlflow_enabled:
            for k, v in {**prefixed_train, **prefixed_test}.items():
                mlflow.log_metric(k, v)

        # ==============================================================
        # Model comparison
        # ==============================================================
        logger.info("--- Model Comparison (TEST set) ---")
        if preds["lgbm_test"] is not None:
            lgbm_f1 = lgbm_test_m["f1_macro"]
            rf_f1 = rf_test_m["f1_macro"]

            if lgbm_f1 > rf_f1:
                best_model = "LightGBM"
                improvement = ((lgbm_f1 - rf_f1) / rf_f1) * 100 if rf_f1 > 0 else 0
            else:
                best_model = "RandomForest"
                improvement = ((rf_f1 - lgbm_f1) / lgbm_f1) * 100 if lgbm_f1 > 0 else 0

            logger.info("  LightGBM F1-macro:  %.4f", lgbm_f1)
            logger.info("  RF F1-macro:        %.4f", rf_f1)
            logger.info("  Best model: %s (%.1f%% better)", best_model, improvement)
            all_metrics["best_model"] = best_model
            all_metrics["improvement_pct"] = round(improvement, 2)

            if mlflow_enabled:
                mlflow.log_param("best_model", best_model)
                mlflow.log_metric("improvement_pct", round(improvement, 2))

            # Agreement
            agreement = (preds["lgbm_test"] == preds["rf_test"]).mean()
            logger.info("  Model agreement: %.1f%%", 100 * agreement)
        else:
            logger.info("  Only RF available (LightGBM not installed)")

        # ==============================================================
        # Save metrics report
        # ==============================================================
        numeric_metrics = {
            k: v for k, v in all_metrics.items() if isinstance(v, (int, float))
        }
        report_df = pd.DataFrame(
            list(numeric_metrics.items()), columns=["Metric", "Value"]
        )
        report_path = report_dir / "evaluation_metrics.csv"
        report_df.to_csv(report_path, index=False)
        logger.info("  Metrics report saved to %s", report_path)

        if mlflow_enabled:
            mlflow.log_artifact(str(report_path))
            # Also log confusion matrix and classification report if they exist
            cm_path = report_dir / "confusion_matrix.csv"
            if cm_path.exists():
                mlflow.log_artifact(str(cm_path))
            cr_path = report_dir / "classification_report.txt"
            if cr_path.exists():
                mlflow.log_artifact(str(cr_path))
            logger.info("  MLflow run ID: %s", ml_run.info.run_id)

    logger.info("=" * 60)
    logger.info("CREDIT RISK EVALUATION - COMPLETE")
    logger.info("=" * 60)

    return all_metrics


class _nullcontext:
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass


if __name__ == "__main__":
    from steps.credit_risk.input_format import run as input_run
    from steps.credit_risk.preprocessing import run as preprocess_run
    from steps.credit_risk.model_training import run as train_run

    merged = input_run()
    preprocessed = preprocess_run(merged)
    trained = train_run(preprocessed)
    metrics = run(trained)
