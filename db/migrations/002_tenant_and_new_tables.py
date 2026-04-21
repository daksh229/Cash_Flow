"""
Migration 002 - Multi-tenancy + new tables
==========================================
Adds `tenant_id` to existing tables and introduces:
  - non_po_expenses
  - actual_outcomes

For SQLite we rely on create_all (idempotent) + a best-effort ALTER for
the tenant_id columns on pre-existing tables. On Postgres you should
route real schema migrations through Alembic once this lands.

Run:
    python -m db.migrations.002_tenant_and_new_tables
"""

import logging

from sqlalchemy import inspect, text

from db.connection import get_engine
from db.schema import Base
import db.models  # noqa: F401

logger = logging.getLogger(__name__)

LEGACY_TABLES = ("feature_snapshots", "forecast_outputs", "run_audit", "event_log")


def _add_tenant_column_if_missing(engine):
    insp = inspect(engine)
    with engine.begin() as conn:
        for table in LEGACY_TABLES:
            if not insp.has_table(table):
                continue
            cols = {c["name"] for c in insp.get_columns(table)}
            if "tenant_id" in cols:
                continue
            logger.info("adding tenant_id to %s", table)
            conn.execute(text(
                f"ALTER TABLE {table} ADD COLUMN tenant_id VARCHAR(32) "
                f"NOT NULL DEFAULT 'default'"
            ))


def run():
    engine = get_engine()
    _add_tenant_column_if_missing(engine)
    Base.metadata.create_all(engine)
    tables = list(Base.metadata.tables.keys())
    logger.info("migration 002 complete (%d tables registered)", len(tables))
    return tables


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("Tables:", run())
