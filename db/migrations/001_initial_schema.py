"""
Migration 001 - Initial Schema
==============================
Creates all tables defined in db.models. Safe to run multiple times
(create_all is idempotent).

Run:
    python -m db.migrations.001_initial_schema
"""

import logging

from db.connection import get_engine
from db.schema import Base
import db.models  # noqa: F401 - register models on Base.metadata

logger = logging.getLogger(__name__)


def run():
    engine = get_engine()
    Base.metadata.create_all(engine)
    logger.info("Initial schema created (%d tables)", len(Base.metadata.tables))
    return list(Base.metadata.tables.keys())


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    tables = run()
    print("Tables created:", tables)
