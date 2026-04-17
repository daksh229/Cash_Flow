"""
Pipeline Runner - S7 Cash Event Normalisation & Aggregation
"""

import sys, logging, yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from steps.s7_cash_aggregation.input_format import run as input_run
from steps.s7_cash_aggregation.forecast_engine import run as engine_run
from steps.s7_cash_aggregation.output import run as output_run

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(levelname)s | %(message)s")
logger = logging.getLogger("pipeline.s7")


def main():
    with open(PROJECT_ROOT / "config.yml") as f:
        master_cfg = yaml.safe_load(f)
    with open(PROJECT_ROOT / "config" / "s7_cash_aggregation.yml") as f:
        model_cfg = yaml.safe_load(f)

    logger.info("#" * 60)
    logger.info("PIPELINE: S7 Cash Aggregation - START")
    logger.info("#" * 60)

    logger.info(">>> STEP 1/3: Input Format (Ingest + Standardise)")
    data = input_run(config=model_cfg)

    logger.info(">>> STEP 2/3: Aggregation Engine (Dedup + Aggregate + Cumulative)")
    result = engine_run(data, config=model_cfg)

    logger.info(">>> STEP 3/3: Output (Publish)")
    summary = output_run(result, config=model_cfg, master_cfg=master_cfg)

    logger.info("#" * 60)
    logger.info("PIPELINE: S7 Cash Aggregation - COMPLETE")
    logger.info("#" * 60)

    return summary


if __name__ == "__main__":
    main()
