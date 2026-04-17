"""
Pipeline Runner - Credit Risk Assessment
============================================
Runs the full Credit Risk pipeline with config:
  1. Input Format  (load customer_features + target)
  2. Preprocessing (encode target, stratified split)
  3. Model Training (LightGBM + RF classifiers with MLflow)
  4. Evaluation    (accuracy, F1, confusion matrix, AUC-ROC)
"""

import sys
import logging
import yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from steps.credit_risk.input_format import run as input_format_run
from steps.credit_risk.preprocessing import run as preprocessing_run
from steps.credit_risk.model_training import run as model_training_run
from steps.credit_risk.evaluate import run as evaluate_run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("pipeline.credit_risk")


def _load_configs():
    master_path = PROJECT_ROOT / "config.yml"
    model_path = PROJECT_ROOT / "config" / "credit_risk.yml"

    with open(master_path, "r") as f:
        master_cfg = yaml.safe_load(f)
    with open(model_path, "r") as f:
        model_cfg = yaml.safe_load(f)

    return master_cfg, model_cfg


def main():
    master_cfg, model_cfg = _load_configs()

    logger.info("#" * 60)
    logger.info("PIPELINE: Credit Risk Assessment - START")
    logger.info("#" * 60)

    logger.info("")
    logger.info(">>> STEP 1/4: Input Format")
    merged_df = input_format_run(config=model_cfg)

    logger.info("")
    logger.info(">>> STEP 2/4: Preprocessing")
    preprocessed = preprocessing_run(merged_df, config=model_cfg)

    logger.info("")
    logger.info(">>> STEP 3/4: Model Training")
    training_result = model_training_run(
        preprocessed, config=model_cfg, master_cfg=master_cfg
    )

    logger.info("")
    logger.info(">>> STEP 4/4: Evaluation")
    metrics = evaluate_run(
        training_result, config=model_cfg, master_cfg=master_cfg
    )

    logger.info("")
    logger.info("#" * 60)
    logger.info("PIPELINE: Credit Risk Assessment - COMPLETE")
    logger.info("#" * 60)
    logger.info("")
    logger.info("=== FINAL RESULTS ===")
    for key, value in sorted(metrics.items()):
        if isinstance(value, (int, float)):
            logger.info("  %-35s %.4f", key, value)
        else:
            logger.info("  %-35s %s", key, value)

    return metrics


if __name__ == "__main__":
    main()
