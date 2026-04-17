"""
Pipeline Runner - S4 Sales Pipeline Forecast
================================================
Runs the full S4 pipeline:
  1. Input Format    (CRM deals + customer delays + cohort stats)
  2. Forecast Engine (stage probability x milestone extrapolation)
  3. Output          (detailed + forecast_outputs + summary)
"""

import sys
import logging
import yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from steps.s4_pipeline_forecast.input_format import run as input_format_run
from steps.s4_pipeline_forecast.forecast_engine import run as forecast_engine_run
from steps.s4_pipeline_forecast.output import run as output_run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("pipeline.s4")


def _load_configs():
    master_path = PROJECT_ROOT / "config.yml"
    model_path = PROJECT_ROOT / "config" / "s4_pipeline_forecast.yml"

    with open(master_path, "r") as f:
        master_cfg = yaml.safe_load(f)
    with open(model_path, "r") as f:
        model_cfg = yaml.safe_load(f)

    return master_cfg, model_cfg


def main():
    master_cfg, model_cfg = _load_configs()

    logger.info("#" * 60)
    logger.info("PIPELINE: S4 Sales Pipeline Forecast - START")
    logger.info("#" * 60)

    logger.info("")
    logger.info(">>> STEP 1/3: Input Format")
    input_data = input_format_run(config=model_cfg)

    logger.info("")
    logger.info(">>> STEP 2/3: Forecast Engine")
    forecast = forecast_engine_run(input_data, config=model_cfg)

    logger.info("")
    logger.info(">>> STEP 3/3: Output")
    summary = output_run(forecast, config=model_cfg, master_cfg=master_cfg)

    logger.info("")
    logger.info("#" * 60)
    logger.info("PIPELINE: S4 Sales Pipeline Forecast - COMPLETE")
    logger.info("#" * 60)

    return summary


if __name__ == "__main__":
    main()
