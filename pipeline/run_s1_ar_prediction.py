"""
Pipeline Runner - S1 AR Collections Prediction
================================================
Runs the full S1 pipeline with config:
  1. Input Format  (merge feature tables)
  2. Preprocessing (derive target, encode, split)
  3. Model Training (LightGBM + RF with MLflow)
  4. Evaluation    (metrics, comparison, report)

Can be run standalone or called from main.py / run_all.py.
"""

import sys
import logging
import yaml
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from steps.s1_ar_prediction.input_format import run as input_format_run
from steps.s1_ar_prediction.preprocessing import run as preprocessing_run
from steps.s1_ar_prediction.model_training import run as model_training_run
from steps.s1_ar_prediction.evaluate import run as evaluate_run

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("pipeline.s1")


def _load_configs():
    """Load master and model configs."""
    master_path = PROJECT_ROOT / "config.yml"
    model_path = PROJECT_ROOT / "config" / "s1_ar_prediction.yml"

    with open(master_path, "r") as f:
        master_cfg = yaml.safe_load(f)
    with open(model_path, "r") as f:
        model_cfg = yaml.safe_load(f)

    return master_cfg, model_cfg


def main():
    master_cfg, model_cfg = _load_configs()

    logger.info("#" * 60)
    logger.info("PIPELINE: S1 AR Collections Prediction - START")
    logger.info("#" * 60)

    # Step 1: Input Format
    logger.info("")
    logger.info(">>> STEP 1/4: Input Format")
    merged_df = input_format_run(config=model_cfg)

    # Step 2: Preprocessing
    logger.info("")
    logger.info(">>> STEP 2/4: Preprocessing")
    preprocessed = preprocessing_run(merged_df, config=model_cfg)

    # Step 3: Model Training
    logger.info("")
    logger.info(">>> STEP 3/4: Model Training")
    training_result = model_training_run(
        preprocessed, config=model_cfg, master_cfg=master_cfg
    )

    # Step 4: Evaluation
    logger.info("")
    logger.info(">>> STEP 4/4: Evaluation")
    metrics = evaluate_run(
        training_result, config=model_cfg, master_cfg=master_cfg
    )

    # Summary
    logger.info("")
    logger.info("#" * 60)
    logger.info("PIPELINE: S1 AR Collections Prediction - COMPLETE")
    logger.info("#" * 60)
    logger.info("")
    logger.info("=== FINAL RESULTS ===")
    for key, value in sorted(metrics.items()):
        if isinstance(value, (int, float)):
            logger.info("  %-35s %.3f", key, value)
        else:
            logger.info("  %-35s %s", key, value)

    return metrics


if __name__ == "__main__":
    main()
