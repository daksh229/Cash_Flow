"""
Pipeline Runner - S3 WIP Billing Forecast
============================================
Runs the full S3 pipeline:
  1. Input Format    (load milestones + customer features, filter)
  2. Forecast Engine (rule-based: completion -> invoice -> cash date)
  3. Output          (save forecast, generate summary)
"""

import sys
import logging
import yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from steps.s3_wip_forecast.input_format import run as input_format_run
from steps.s3_wip_forecast.forecast_engine import run as forecast_engine_run
from steps.s3_wip_forecast.output import run as output_run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("pipeline.s3")


def _load_configs():
    master_path = PROJECT_ROOT / "config.yml"
    model_path = PROJECT_ROOT / "config" / "s3_wip_forecast.yml"

    with open(master_path, "r") as f:
        master_cfg = yaml.safe_load(f)
    with open(model_path, "r") as f:
        model_cfg = yaml.safe_load(f)

    return master_cfg, model_cfg


def main():
    master_cfg, model_cfg = _load_configs()

    logger.info("#" * 60)
    logger.info("PIPELINE: S3 WIP Billing Forecast - START")
    logger.info("#" * 60)

    logger.info("")
    logger.info(">>> STEP 1/3: Input Format")
    milestones = input_format_run(config=model_cfg)

    logger.info("")
    logger.info(">>> STEP 2/3: Forecast Engine")
    forecast = forecast_engine_run(milestones, config=model_cfg)

    logger.info("")
    logger.info(">>> STEP 3/3: Output")
    summary = output_run(forecast, config=model_cfg, master_cfg=master_cfg)

    logger.info("")
    logger.info("#" * 60)
    logger.info("PIPELINE: S3 WIP Billing Forecast - COMPLETE")
    logger.info("#" * 60)

    return summary


if __name__ == "__main__":
    main()
