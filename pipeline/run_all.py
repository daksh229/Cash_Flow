"""
Pipeline Runner - Run All Models
==================================
Master orchestrator that runs:
  1. Feature Table Generation (common, once)
  2. S1 AR Collections Prediction
  3. S2 AP Payment Prediction (TODO)
  4. Credit Risk Assessment (TODO)
"""

import sys
import logging
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("pipeline.run_all")


def main():
    logger.info("=" * 70)
    logger.info("MASTER PIPELINE - START")
    logger.info("=" * 70)

    # ------------------------------------------------------------------
    # Step 1: Feature Table Generation (common)
    # ------------------------------------------------------------------
    logger.info("")
    logger.info(">>> [1/4] Feature Table Generation")
    from steps.feature_table import run as feature_table_run
    feature_table_run()

    # ------------------------------------------------------------------
    # Step 2: S1 AR Collections Prediction
    # ------------------------------------------------------------------
    logger.info("")
    logger.info(">>> [2/4] S1 AR Collections Prediction")
    from pipeline.run_s1_ar_prediction import main as s1_main
    s1_metrics = s1_main()

    # ------------------------------------------------------------------
    # Step 3: S2 AP Payment Prediction (TODO)
    # ------------------------------------------------------------------
    logger.info("")
    logger.info(">>> [3/4] S2 AP Payment Prediction - SKIPPED (not yet implemented)")

    # ------------------------------------------------------------------
    # Step 4: Credit Risk Assessment (TODO)
    # ------------------------------------------------------------------
    logger.info("")
    logger.info(">>> [4/4] Credit Risk Assessment - SKIPPED (not yet implemented)")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    logger.info("")
    logger.info("=" * 70)
    logger.info("MASTER PIPELINE - COMPLETE")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
