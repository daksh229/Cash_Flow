"""
Pipeline Runner - S5 Contingent Inflows
"""

import sys, logging, yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from steps.s5_contingent_inflows.input_format import run as input_run
from steps.s5_contingent_inflows.forecast_engine import run as engine_run
from steps.s5_contingent_inflows.output import run as output_run

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(levelname)s | %(message)s")
logger = logging.getLogger("pipeline.s5")


def main():
    with open(PROJECT_ROOT / "config.yml") as f:
        master_cfg = yaml.safe_load(f)
    with open(PROJECT_ROOT / "config" / "s5_contingent_inflows.yml") as f:
        model_cfg = yaml.safe_load(f)

    logger.info("# PIPELINE: S5 Contingent Inflows - START")

    logger.info(">>> STEP 1/3: Input Format")
    data = input_run(config=model_cfg)

    logger.info(">>> STEP 2/3: Forecast Engine")
    forecast = engine_run(data, config=model_cfg)

    logger.info(">>> STEP 3/3: Output")
    summary = output_run(forecast, config=model_cfg, master_cfg=master_cfg)

    logger.info("# PIPELINE: S5 Contingent Inflows - COMPLETE")
    return summary


if __name__ == "__main__":
    main()
