"""
Migration 003 - Partials improvements
=====================================
Adds:
  - feature_versions          (Q4 version policy)
  - recommendation_feedback   (Q11 feedback loop)
  - model_registry            (Q9 promotion states)
  - ingestion_dlq             (Q5a dead-letter queue)
  - ingestion_seen            (Q5a idempotency)

Run:
    python -m db.migrations.003_partials_improvements
"""

import logging

from db.connection import get_engine
from db.schema import Base
import db.models  # noqa: F401

logger = logging.getLogger(__name__)


def run():
    engine = get_engine()
    Base.metadata.create_all(engine)
    logger.info("migration 003 complete")
    return list(Base.metadata.tables.keys())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Tables:", run())
