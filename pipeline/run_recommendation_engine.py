"""
Pipeline Runner - Recommendation Engine
"""

import sys, logging, yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from steps.recommendation_engine.input_format import run as input_run
from steps.recommendation_engine.forecast_engine import run as engine_run
from steps.recommendation_engine.output import run as output_run

logging.basicConfig(level=logging.INFO, format="%(asctime)s | %(name)s | %(levelname)s | %(message)s")
logger = logging.getLogger("pipeline.re")


def main():
    with open(PROJECT_ROOT / "config.yml") as f:
        master_cfg = yaml.safe_load(f)
    with open(PROJECT_ROOT / "config" / "recommendation_engine.yml") as f:
        model_cfg = yaml.safe_load(f)

    logger.info("#" * 60)
    logger.info("PIPELINE: Recommendation Engine - START")
    logger.info("#" * 60)

    logger.info(">>> STEP 1/3: Input Format")
    data = input_run(config=model_cfg)

    logger.info(">>> STEP 2/3: Engine (Scenarios + Scoring + Ranking)")
    recs = engine_run(data, config=model_cfg)

    logger.info(">>> STEP 3/3: Output")
    summary = output_run(recs, config=model_cfg, master_cfg=master_cfg)

    logger.info("#" * 60)
    logger.info("PIPELINE: Recommendation Engine - COMPLETE")
    logger.info("#" * 60)

    return summary


if __name__ == "__main__":
    main()
