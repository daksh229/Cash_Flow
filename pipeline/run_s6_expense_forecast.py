"""
Pipeline Runner - S6 Expense Forecast
"""

import sys, logging, yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from steps.s6_expense_forecast.input_format import run as input_run
from steps.s6_expense_forecast.forecast_engine import run as engine_run
from steps.s6_expense_forecast.output import run as output_run

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(levelname)s | %(message)s")
logger = logging.getLogger("pipeline.s6")


def main():
    with open(PROJECT_ROOT / "config.yml") as f:
        master_cfg = yaml.safe_load(f)
    with open(PROJECT_ROOT / "config" / "s6_expense_forecast.yml") as f:
        model_cfg = yaml.safe_load(f)

    logger.info("# PIPELINE: S6 Expense Forecast - START")

    logger.info(">>> STEP 1/3: Input Format")
    data = input_run(config=model_cfg)

    logger.info(">>> STEP 2/3: Forecast Engine")
    forecast = engine_run(data, config=model_cfg)

    logger.info(">>> STEP 3/3: Output")
    summary = output_run(forecast, config=model_cfg, master_cfg=master_cfg)

    logger.info("# PIPELINE: S6 Expense Forecast - COMPLETE")
    return summary


if __name__ == "__main__":
    main()
