"""
Database engine + session plumbing.

SQLite for now -- zero setup, a real file on disk, good enough for a single
instance. Everything here is written against plain SQLAlchemy Core/ORM, so
moving to Postgres later is a one-line change to DATABASE_URL plus a
`pip install psycopg2-binary`; none of the model or route code would need
to change.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

DATA_DIR = Path(__file__).resolve().parent / "data"
DATA_DIR.mkdir(exist_ok=True)

DATABASE_URL = os.environ.get("CODECANVAS_DATABASE_URL", f"sqlite:///{DATA_DIR / 'codecanvas.db'}")

# Render (and Heroku, and others) hand out connection strings as
# "postgres://...", which SQLAlchemy 2.0 rejects outright
# (ArgumentError: Could not parse SQLAlchemy URL) -- it only accepts
# "postgresql://". Pin the driver explicitly to +psycopg2 too (that's the
# one the Dockerfile installs) rather than let SQLAlchemy guess between
# psycopg2/psycopg3 based on whatever happens to be importable.
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg2://", 1)
elif DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg2://", 1)

connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, connect_args=connect_args)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


class Base(DeclarativeBase):
    pass


def get_db():
    db: Session = SessionLocal()
    try:
        yield db
    finally:
        db.close()
