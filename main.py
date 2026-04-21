"""
Cash Flow Forecasting Model - Main Entry Point
=================================================
Reads config.yml, loads per-model configs, and orchestrates
the full pipeline: feature generation -> model training -> evaluation.

Usage:
    python main.py                         # run with default config.yml
    python main.py --config my_config.yml  # run with custom config
"""

import sys
import os
import argparse
import logging
import yaml
from pathlib import Path

# Project root
PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))


def _setup_logging(level_str):
    """Configure root logger."""
    level = getattr(logging, level_str.upper(), logging.INFO)
    logging.basicConfig(
        level=level,
        format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
        force=True,
    )
    return logging.getLogger("main")


def _load_config(config_path):
    """Load master config.yml."""
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def _load_model_config(model_key):
    """Load per-model config from config/ folder."""
    config_path = PROJECT_ROOT / "config" / f"{model_key}.yml"
    if not config_path.exists():
        raise FileNotFoundError(f"Model config not found: {config_path}")
    with open(config_path, "r") as f:
        return yaml.safe_load(f)


def _run_feature_table(global_cfg):
    """Run common feature table generation."""
    import pandas as pd
    from steps.feature_table import run as feature_table_run

    # Pass reference date from config
    import steps.feature_table as ft_module
    ref_date = global_cfg.get("reference_date", "2026-04-15")
    ft_module.REFERENCE_DATE = pd.Timestamp(ref_date)

    return feature_table_run()


def _run_model_pipeline(model_key, master_cfg, model_cfg):
    """Run a single model's full pipeline using its config."""
    logger = logging.getLogger(f"main.{model_key}")

    model_name = model_cfg["model_info"]["name"]
    model_type = model_cfg["model_info"]["type"]

    logger.info("=" * 60)
    logger.info("MODEL: %s (%s)", model_name, model_type)
    logger.info("=" * 60)

    if model_type == "rule_based":
        return _run_forecast_pipeline(model_key, master_cfg, model_cfg, logger)
    else:
        return _run_prediction_pipeline(model_key, master_cfg, model_cfg, logger)


def _run_prediction_pipeline(model_key, master_cfg, model_cfg, logger):
    """Run ML prediction pipeline: input -> preprocess -> train -> evaluate."""
    input_format_mod = __import__(
        f"steps.{model_key}.input_format", fromlist=["run"]
    )
    preprocessing_mod = __import__(
        f"steps.{model_key}.preprocessing", fromlist=["run"]
    )
    model_training_mod = __import__(
        f"steps.{model_key}.model_training", fromlist=["run"]
    )
    evaluate_mod = __import__(
        f"steps.{model_key}.evaluate", fromlist=["run"]
    )

    logger.info(">>> Step 1/4: Input Format")
    merged_df = input_format_mod.run(model_cfg)

    logger.info(">>> Step 2/4: Preprocessing")
    preprocessed = preprocessing_mod.run(merged_df, model_cfg)

    logger.info(">>> Step 3/4: Model Training")
    training_result = model_training_mod.run(preprocessed, model_cfg, master_cfg)

    logger.info(">>> Step 4/4: Evaluation")
    metrics = evaluate_mod.run(training_result, model_cfg, master_cfg)

    model_name = model_cfg["model_info"]["name"]
    logger.info("=" * 60)
    logger.info("MODEL: %s - COMPLETE", model_name)
    logger.info("=" * 60)

    return metrics


def _run_forecast_pipeline(model_key, master_cfg, model_cfg, logger):
    """Run rule-based forecast pipeline: input -> engine -> output."""
    input_format_mod = __import__(
        f"steps.{model_key}.input_format", fromlist=["run"]
    )
    forecast_engine_mod = __import__(
        f"steps.{model_key}.forecast_engine", fromlist=["run"]
    )
    output_mod = __import__(
        f"steps.{model_key}.output", fromlist=["run"]
    )

    logger.info(">>> Step 1/3: Input Format")
    input_data = input_format_mod.run(model_cfg)

    logger.info(">>> Step 2/3: Forecast Engine")
    forecast = forecast_engine_mod.run(input_data, model_cfg)

    logger.info(">>> Step 3/3: Output")
    summary = output_mod.run(forecast, model_cfg, master_cfg)

    model_name = model_cfg["model_info"]["name"]
    logger.info("=" * 60)
    logger.info("MODEL: %s - COMPLETE", model_name)
    logger.info("=" * 60)

    return summary


def main():
    # ------------------------------------------------------------------
    # Parse arguments
    # ------------------------------------------------------------------
    parser = argparse.ArgumentParser(description="Cash Flow Forecasting Pipeline")
    parser.add_argument(
        "--config", type=str, default="config.yml",
        help="Path to master config file (default: config.yml)",
    )
    args = parser.parse_args()

    # ------------------------------------------------------------------
    # Load master config
    # ------------------------------------------------------------------
    config_path = PROJECT_ROOT / args.config
    master_cfg = _load_config(config_path)
    global_cfg = master_cfg["global"]

    logger = _setup_logging(global_cfg.get("log_level", "INFO"))

    logger.info("#" * 70)
    logger.info("CASH FLOW FORECASTING MODEL - PIPELINE START")
    logger.info("#" * 70)
    logger.info("Config: %s", config_path)
    logger.info("Models to run: %s", master_cfg.get("models", []))

    # Need pandas for reference date
    global pd
    import pandas as pd

    # Set random seed
    seed = global_cfg.get("random_seed", 42)
    import numpy as np
    np.random.seed(seed)
    logger.info("Random seed: %d", seed)

    # ------------------------------------------------------------------
    # Step 1: Feature Table Generation
    # ------------------------------------------------------------------
    if master_cfg.get("feature_table", {}).get("run", True):
        logger.info("")
        logger.info(">>> PHASE 1: Feature Table Generation")
        _run_feature_table(global_cfg)
    else:
        logger.info(">>> PHASE 1: Feature Table Generation - SKIPPED (run=false)")

    # ------------------------------------------------------------------
    # Step 2: Run each enabled model
    # ------------------------------------------------------------------
    models_to_run = master_cfg.get("models", [])
    all_results = {}

    for idx, model_key in enumerate(models_to_run, 1):
        logger.info("")
        logger.info(
            ">>> PHASE 2: Model %d/%d - %s", idx, len(models_to_run), model_key
        )

        try:
            model_cfg = _load_model_config(model_key)
            metrics = _run_model_pipeline(model_key, master_cfg, model_cfg)
            all_results[model_key] = {"status": "SUCCESS", "metrics": metrics}
        except Exception as e:
            logger.error("Model %s FAILED: %s", model_key, str(e), exc_info=True)
            all_results[model_key] = {"status": "FAILED", "error": str(e)}

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    logger.info("")
    logger.info("#" * 70)
    logger.info("PIPELINE SUMMARY")
    logger.info("#" * 70)

    for model_key, result in all_results.items():
        status = result["status"]
        if status == "SUCCESS":
            metrics = result["metrics"]
            # Show key metric
            key_metrics = {
                k: v for k, v in metrics.items()
                if "test_mae" in k or "test_f1" in k or "test_accuracy" in k
            }
            logger.info(
                "  %-30s %s  %s", model_key, status, key_metrics or ""
            )
        else:
            logger.info("  %-30s %s  Error: %s", model_key, status, result["error"])

    logger.info("#" * 70)
    logger.info("CASH FLOW FORECASTING MODEL - PIPELINE COMPLETE")
    logger.info("#" * 70)

    return all_results


if __name__ == "__main__":
    main()
