"""
S1 AR Collections Prediction - Evaluation
===========================================
Evaluates LightGBM and Random Forest models on train and test data.
Metrics and thresholds are read from config. Logs results to MLflow.
"""

import os
import logging
import yaml
import numpy as np
import pandas as pd
import mlflow
from pathlib import Path
from sklearn.metrics import (
    mean_absolute_error,
    mean_squared_error,
    r2_score,
    median_absolute_error,
)

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------
logger = logging.getLogger("s1.evaluate")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent.parent
CONFIG_PATH = BASE_DIR / "config" / "s1_ar_prediction.yml"


def _load_default_config():
    with open(CONFIG_PATH, "r") as f:
        return yaml.safe_load(f)


def _compute_metrics(y_true, y_pred, metrics_list):
    """Compute requested regression metrics."""
    results = {}

    metric_fns = {
        "mae": lambda yt, yp: mean_absolute_error(yt, yp),
        "rmse": lambda yt, yp: np.sqrt(mean_squared_error(yt, yp)),
        "r2": lambda yt, yp: r2_score(yt, yp),
        "median_ae": lambda yt, yp: median_absolute_error(yt, yp),
        "mape": lambda yt, yp: (
            np.mean(np.abs((yt[yt != 0] - yp[yt != 0]) / yt[yt != 0])) * 100
            if (yt != 0).sum() > 0 else 0.0
        ),
    }

    for metric_name in metrics_list:
        if metric_name in metric_fns:
            results[metric_name] = round(metric_fns[metric_name](y_true, y_pred), 3)

    return results


def _log_metrics_table(metrics, model_name, split_name):
    """Log formatted metrics table."""
    logger.info("  %s - %s:", model_name, split_name)
    logger.info("    %-20s %s", "Metric", "Value")
    logger.info("    %s", "-" * 35)
    for key, val in metrics.items():
        logger.info("    %-20s %.3f", key.upper(), val)


def run(training_result, config=None, master_cfg=None):
    """
    Evaluate models and log results.

    Parameters
    ----------
    training_result : dict
        Output from model_training.run()
    config : dict or None
        Model config.
    master_cfg : dict or None
        Master config.

    Returns
    -------
    dict with all evaluation metrics
    """
    if config is None:
        config = _load_default_config()
    if master_cfg is None:
        master_cfg = {}

    logger.info("=" * 60)
    logger.info("S1 EVALUATION - START")
    logger.info("=" * 60)

    # Read eval config
    eval_cfg = config.get("evaluation", {})
    metrics_list = eval_cfg.get("metrics", ["mae", "rmse", "r2", "mape", "median_ae"])
    error_buckets = eval_cfg.get("error_buckets", [3, 7, 14, 30])
    overfit_threshold = eval_cfg.get("overfit_threshold", 1.5)
    divergence_threshold = eval_cfg.get("divergence_threshold", 10)

    # Report directory
    global_cfg = master_cfg.get("global", {})
    report_dir = BASE_DIR / global_cfg.get("report_dir", "reports") / "s1_ar_prediction"
    os.makedirs(report_dir, exist_ok=True)

    y_train = training_result["y_train"].values
    y_test = training_result["y_test"].values
    preds = training_result["predictions"]

    all_metrics = {}

    # ------------------------------------------------------------------
    # MLflow setup
    # ------------------------------------------------------------------
    mlflow_cfg = master_cfg.get("mlflow", {})
    mlflow_enabled = mlflow_cfg.get("enabled", True)

    if mlflow_enabled:
        tracking_path = BASE_DIR / mlflow_cfg.get("tracking_uri", "mlruns")
        tracking_uri = tracking_path.as_uri()  # file:///... format
        experiment_prefix = mlflow_cfg.get("experiment_prefix", "CashFlow")
        mlflow.set_tracking_uri(tracking_uri)
        mlflow.set_experiment(f"{experiment_prefix}_S1_AR_Prediction")

    run_context = (
        mlflow.start_run(run_name="s1_evaluation")
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

            lgbm_train_m = _compute_metrics(y_train, preds["lgbm_train"], metrics_list)
            prefixed_train = {f"lgbm_train_{k}": v for k, v in lgbm_train_m.items()}
            _log_metrics_table(lgbm_train_m, "LightGBM", "TRAIN")
            all_metrics.update(prefixed_train)

            lgbm_test_m = _compute_metrics(y_test, preds["lgbm_test"], metrics_list)
            prefixed_test = {f"lgbm_test_{k}": v for k, v in lgbm_test_m.items()}
            _log_metrics_table(lgbm_test_m, "LightGBM", "TEST")
            all_metrics.update(prefixed_test)

            if mlflow_enabled:
                for k, v in {**prefixed_train, **prefixed_test}.items():
                    mlflow.log_metric(k, v)

            # Overfitting check
            train_mae = lgbm_train_m.get("mae", 0)
            test_mae = lgbm_test_m.get("mae", 0)
            overfit_ratio = test_mae / train_mae if train_mae > 0 else 1.0
            all_metrics["lgbm_overfit_ratio"] = round(overfit_ratio, 3)

            if overfit_ratio > overfit_threshold:
                logger.warning(
                    "  OVERFIT WARNING: test/train MAE ratio = %.2f (threshold: %.1f)",
                    overfit_ratio, overfit_threshold,
                )
            else:
                logger.info(
                    "  Overfit check OK: test/train MAE ratio = %.2f", overfit_ratio
                )

        # ==============================================================
        # Random Forest evaluation
        # ==============================================================
        logger.info("--- Random Forest Evaluation ---")

        rf_train_m = _compute_metrics(y_train, preds["rf_train"], metrics_list)
        prefixed_train = {f"rf_train_{k}": v for k, v in rf_train_m.items()}
        _log_metrics_table(rf_train_m, "Random Forest", "TRAIN")
        all_metrics.update(prefixed_train)

        rf_test_m = _compute_metrics(y_test, preds["rf_test"], metrics_list)
        prefixed_test = {f"rf_test_{k}": v for k, v in rf_test_m.items()}
        _log_metrics_table(rf_test_m, "Random Forest", "TEST")
        all_metrics.update(prefixed_test)

        if mlflow_enabled:
            for k, v in {**prefixed_train, **prefixed_test}.items():
                mlflow.log_metric(k, v)

        # ==============================================================
        # Model comparison
        # ==============================================================
        if preds["lgbm_test"] is not None:
            logger.info("--- Model Comparison (TEST set) ---")
            lgbm_mae = lgbm_test_m.get("mae", 0)
            rf_mae = rf_test_m.get("mae", 0)

            if lgbm_mae < rf_mae:
                best_model = "LightGBM"
                improvement = ((rf_mae - lgbm_mae) / rf_mae) * 100
            else:
                best_model = "RandomForest"
                improvement = ((lgbm_mae - rf_mae) / lgbm_mae) * 100

            logger.info("  LightGBM MAE:  %.3f", lgbm_mae)
            logger.info("  RF MAE:        %.3f", rf_mae)
            logger.info("  Best model: %s (%.1f%% better)", best_model, improvement)
            all_metrics["best_model"] = best_model
            all_metrics["improvement_pct"] = round(improvement, 2)

            if mlflow_enabled:
                mlflow.log_param("best_model", best_model)
                mlflow.log_metric("improvement_pct", round(improvement, 2))

            # Divergence analysis
            divergence = np.abs(preds["lgbm_test"] - preds["rf_test"])
            logger.info("  Model divergence (test):")
            logger.info("    Mean:   %.2f days", divergence.mean())
            logger.info("    Median: %.2f days", np.median(divergence))
            logger.info("    Max:    %.2f days", divergence.max())
            high_div = (divergence > divergence_threshold).sum()
            logger.info(
                "    >%d days divergence: %d / %d (%.1f%%)",
                divergence_threshold, high_div, len(divergence),
                100 * high_div / len(divergence),
            )

        # ==============================================================
        # Error distribution by buckets from config
        # ==============================================================
        logger.info("--- Error Distribution (TEST - primary model) ---")
        if preds["lgbm_test"] is not None:
            errors = y_test - preds["lgbm_test"]
        else:
            errors = y_test - preds["rf_test"]

        abs_errors = np.abs(errors)
        for bucket in error_buckets:
            pct = 100 * (abs_errors <= bucket).mean()
            logger.info("    Within %2d days: %5.1f%%", bucket, pct)
            if mlflow_enabled:
                mlflow.log_metric(f"error_pct_within_{bucket}d", round(pct, 1))

        gt_max = 100 * (abs_errors > error_buckets[-1]).mean()
        logger.info("    > %2d days:      %5.1f%%", error_buckets[-1], gt_max)

        # ==============================================================
        # Accuracy metrics (regression-adapted)
        # ==============================================================
        logger.info("--- Accuracy Metrics (TEST - primary model) ---")

        primary_pred = preds["lgbm_test"] if preds["lgbm_test"] is not None else preds["rf_test"]

        # 1. Tolerance-based accuracy: % predictions within N days of actual
        for tol in [3, 5, 7, 10]:
            acc = 100 * (np.abs(y_test - primary_pred) <= tol).mean()
            key = f"accuracy_within_{tol}d"
            all_metrics[key] = round(acc, 1)
            logger.info("    Accuracy (within %2d days): %5.1f%%", tol, acc)
            if mlflow_enabled:
                mlflow.log_metric(key, round(acc, 1))

        # 2. Directional accuracy: does the model correctly predict
        #    whether payment will be early (<= due) or late (> due)?
        y_mean = y_train.mean()
        actual_direction = (y_test > y_mean).astype(int)
        pred_direction = (primary_pred > y_mean).astype(int)
        direction_acc = 100 * (actual_direction == pred_direction).mean()
        all_metrics["directional_accuracy"] = round(direction_acc, 1)
        logger.info("    Directional accuracy:       %5.1f%%", direction_acc)
        if mlflow_enabled:
            mlflow.log_metric("directional_accuracy", round(direction_acc, 1))

        # 3. Explained variance score
        from sklearn.metrics import explained_variance_score
        evs = explained_variance_score(y_test, primary_pred)
        all_metrics["explained_variance"] = round(evs, 4)
        logger.info("    Explained variance:         %5.4f", evs)
        if mlflow_enabled:
            mlflow.log_metric("explained_variance", round(evs, 4))

        # 4. Mean Bias Error (positive = model predicts too high)
        mbe = float(np.mean(primary_pred - y_test))
        all_metrics["mean_bias_error"] = round(mbe, 3)
        logger.info("    Mean bias error:            %+.3f days", mbe)
        if mlflow_enabled:
            mlflow.log_metric("mean_bias_error", round(mbe, 3))

        # ==============================================================
        # Save payment_predictions output table (SDD schema)
        # ==============================================================
        logger.info("--- Saving Output Tables ---")

        all_meta = training_result.get("all_meta", pd.DataFrame())
        lgbm_all = preds.get("lgbm_all")
        rf_all = preds.get("rf_all")
        forecast_output_dir = BASE_DIR / "Data" / "forecast_outputs"
        os.makedirs(forecast_output_dir, exist_ok=True)

        if not all_meta.empty and lgbm_all is not None:
            import uuid
            ref_date = pd.Timestamp("2026-04-15")

            # payment_predictions table
            pp = all_meta.copy().reset_index(drop=True)
            pp["invoice_date"] = pd.to_datetime(pp["invoice_date"])
            pp["predicted_days_to_pay"] = lgbm_all.round(1)
            pp["predicted_payment_date"] = pp["invoice_date"] + pd.to_timedelta(
                pp["predicted_days_to_pay"].clip(lower=0).astype(int), unit="D"
            )
            pp["baseline_predicted_date"] = pp["invoice_date"] + pd.to_timedelta(
                rf_all.round(0).clip(min=0).astype(int), unit="D"
            ) if rf_all is not None else None

            # Probability buckets (Phase 1: simplified from days_to_pay)
            pp["prob_pay_0_30"] = (pp["predicted_days_to_pay"] <= 30).astype(float)
            pp["prob_pay_30_60"] = (
                (pp["predicted_days_to_pay"] > 30) & (pp["predicted_days_to_pay"] <= 60)
            ).astype(float)
            pp["prob_pay_60_plus"] = (pp["predicted_days_to_pay"] > 60).astype(float)

            pp["expected_payment_amount"] = pp["invoice_amount"]
            pp["trigger_event"] = "BATCH_PREDICTION"

            # Confidence tier from model divergence
            if rf_all is not None:
                div = np.abs(lgbm_all - rf_all)
                pp["confidence_tier"] = np.where(div < 3, "HIGH", np.where(div < 7, "MEDIUM", "LOW"))
            else:
                pp["confidence_tier"] = "MEDIUM"

            pp["prediction_date"] = ref_date.strftime("%Y-%m-%d")
            pp["model_version"] = "lgbm-v1.0"
            pp["transaction_id"] = pp["invoice_id"]
            pp["transaction_type"] = "AR"

            payment_pred_cols = [
                "transaction_id", "transaction_type",
                "predicted_payment_date", "baseline_predicted_date",
                "prob_pay_0_30", "prob_pay_30_60", "prob_pay_60_plus",
                "expected_payment_amount", "trigger_event",
                "confidence_tier", "prediction_date", "model_version",
            ]
            pp_out = pp[[c for c in payment_pred_cols if c in pp.columns]]
            pp_path = forecast_output_dir / "s1_payment_predictions.csv"
            pp_out.to_csv(pp_path, index=False)
            logger.info("  Saved payment_predictions: %s (%d rows)", pp_path, len(pp_out))

            # forecast_outputs table (unified schema for S7)
            fo = pd.DataFrame({
                "forecast_id": [str(uuid.uuid4()) for _ in range(len(pp))],
                "forecast_date": ref_date.strftime("%Y-%m-%d"),
                "forecast_type": "AR",
                "target_date": pp["predicted_payment_date"].dt.strftime("%Y-%m-%d"),
                "forecast_amount": pp["expected_payment_amount"],
                "confidence_low": pp["expected_payment_amount"] * 0.9,
                "confidence_high": pp["expected_payment_amount"] * 1.1,
                "source_module": "S1",
                "forecast_run_id": str(uuid.uuid4()),
            })
            fo_path = forecast_output_dir / "s1_ar_forecast.csv"
            fo.to_csv(fo_path, index=False)
            logger.info("  Saved forecast_outputs: %s (%d rows)", fo_path, len(fo))
        else:
            logger.warning("  No metadata available — skipping output table generation")

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
            logger.info("  MLflow run ID: %s", ml_run.info.run_id)

    logger.info("=" * 60)
    logger.info("S1 EVALUATION - COMPLETE")
    logger.info("=" * 60)

    return all_metrics


class _nullcontext:
    """Minimal no-op context manager for when MLflow is disabled."""
    def __enter__(self):
        return self
    def __exit__(self, *args):
        pass


if __name__ == "__main__":
    from steps.s1_ar_prediction.input_format import run as input_run
    from steps.s1_ar_prediction.preprocessing import run as preprocess_run
    from steps.s1_ar_prediction.model_training import run as train_run

    merged = input_run()
    preprocessed = preprocess_run(merged)
    trained = train_run(preprocessed)
    metrics = run(trained)
