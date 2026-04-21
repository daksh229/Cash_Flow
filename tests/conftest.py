"""
Shared pytest fixtures.

`tmp_db` swaps the DB engine to an ephemeral sqlite file so tests never
touch Data/cashflow.db. `reset_event_bus` clears in-process subscribers
between tests. Import these as `pytest` fixtures by name - pytest wires
them automatically because they live in conftest.
"""

import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))


@pytest.fixture
def tmp_db(tmp_path, monkeypatch):
    import db.connection as conn
    from db.schema import Base
    import db.models  # noqa: F401

    monkeypatch.setenv("CASHFLOW_DB_URL", f"sqlite:///{tmp_path / 'test.db'}")
    conn._engine = None
    conn._SessionFactory = None
    engine = conn.get_engine()
    Base.metadata.create_all(engine)
    yield engine
    conn._engine = None
    conn._SessionFactory = None


@pytest.fixture
def reset_event_bus():
    from events.event_bus import bus
    original = dict(bus._subscribers)
    bus._subscribers.clear()
    yield bus
    bus._subscribers.clear()
    bus._subscribers.update(original)


@pytest.fixture
def tmp_audit_paths(tmp_path, monkeypatch):
    monkeypatch.setenv("CASHFLOW_AUDIT_LOG", str(tmp_path / "audit.jsonl"))
    monkeypatch.setenv("CASHFLOW_LINEAGE_LOG", str(tmp_path / "lineage.jsonl"))
    yield tmp_path
