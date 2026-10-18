"""
Database engine + session plumbing.

SQLite for now -- zero setup, a real file on disk, good enough for a single
instance. Everything here is written against plain SQLAlchemy Core/ORM, so
moving to Postgres later is a one-line change to DATABASE_URL plus a
`pip install psycopg2-binary`; none of the model or route code would need
to change.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
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


def run_lightweight_migrations() -> None:
    """Base.metadata.create_all() (called right before this, in main.py's
    startup) only creates TABLES that don't exist yet -- it never alters a
    table that's already there. That's fine for a fresh SQLite file, but
    Render's Postgres is a real persistent database: a column added to a
    model here (like FsdDraft.intake_validation_json) would otherwise never
    reach the live table, and every insert would start failing with
    "column does not exist" the moment the new code deployed.

    There's no Alembic in this project -- a single-instance demo app with a
    handful of tables doesn't need one yet -- so this does the one thing a
    real migration tool would otherwise be for: diff each model's declared
    columns against what the live table actually has, and ADD COLUMN
    whatever's missing. Additive only (never drops or alters an existing
    column), and each column is added in its own try/except so one failure
    can't block the others or crash startup -- worst case, that one column's
    feature degrades until it's investigated, instead of the whole API going
    down. Safe to run every startup, including against a brand-new database
    where create_all() just created everything (then this is a no-op)."""
    inspector = inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue  # create_all() just made it fresh and correct
            existing = {col["name"] for col in inspector.get_columns(table.name)}
            for column in table.columns:
                if column.name in existing:
                    continue
                try:
                    ddl_type = column.type.compile(dialect=engine.dialect)
                    conn.execute(text(f"ALTER TABLE {table.name} ADD COLUMN {column.name} {ddl_type}"))
                except Exception:
                    logging.getLogger("codecanvas").exception(
                        "migration: failed to add column %s.%s", table.name, column.name
                    )
