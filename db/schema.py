"""
Database Schema - Declarative Base
===================================
SQLAlchemy Base object. All ORM models in db/models.py inherit from this.
Keeping Base in its own module avoids circular imports between models and
the connection layer.
"""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    pass
