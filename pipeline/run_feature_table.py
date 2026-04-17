"""
Pipeline Runner - Feature Table Generation
============================================
Runs the common feature table generation step.
Produces all 6 feature tables in Data/features/.
"""

import sys
import logging
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from steps.feature_table import run

# ---------------------------------------------------------------------------
# Logger
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("pipeline.feature_table")


def main():
    logger.info("=" * 60)
    logger.info("PIPELINE: Feature Table Generation")
    logger.info("=" * 60)

    outputs = run()

    logger.info("Feature tables generated:")
    for name, df in outputs.items():
        logger.info("  %-30s %d rows x %d cols", name, len(df), len(df.columns))

    logger.info("PIPELINE: Feature Table Generation - DONE")


if __name__ == "__main__":
    main()
