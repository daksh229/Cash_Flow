"""
Database Connection Manager
===========================
Provides a singleton engine + session factory for the persisted data layer.
Reads DB settings from config.yml under `database:`.

Usage:
    from db.connection import get_engine, get_session

    with get_session() as session:
        session.add(record)
        session.commit()
"""

import logging
import os
from contextlib import contextmanager
from pathlib import Path

import yaml
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).resolve().parent.parent
_engine = None
_SessionFactory = None


def _load_db_config(config_path=None):
    path = config_path or (PROJECT_ROOT / "config.yml")
    with open(path, "r") as f:
        cfg = yaml.safe_load(f)
    return cfg.get("database", {})


def _build_url(db_cfg):
    url = os.environ.get("CASHFLOW_DB_URL") or db_cfg.get("url")
    if url:
        return url
    backend = db_cfg.get("backend", "sqlite")
    if backend == "sqlite":
        path = db_cfg.get("path", "Data/cashflow.db")
        return f"sqlite:///{PROJECT_ROOT / path}"
    raise ValueError(f"Unsupported backend: {backend}. Set database.url in config.yml")


def get_engine(config_path=None):
    global _engine
    if _engine is None:
        db_cfg = _load_db_config(config_path)
        url = _build_url(db_cfg)
        echo = db_cfg.get("echo", False)
        is_sqlite = url.startswith("sqlite")

        kwargs = {"echo": echo, "future": True}
        if is_sqlite:
            kwargs["connect_args"] = {"check_same_thread": False}
        else:
            kwargs["pool_size"] = db_cfg.get("pool_size", 5)

        _engine = create_engine(url, **kwargs)
        logger.info("DB engine initialised: %s", url.split("@")[-1])
    return _engine


@contextmanager
def get_session():
    global _SessionFactory
    if _SessionFactory is None:
        _SessionFactory = sessionmaker(bind=get_engine(), expire_on_commit=False, future=True)
    session = _SessionFactory()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
