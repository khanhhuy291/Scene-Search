"""Shared SQLAlchemy declarative model base."""

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """Base class for all persistent database models."""
