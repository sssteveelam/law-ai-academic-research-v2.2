from __future__ import annotations

from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url

from models.db import Base


def create_database_engine(database_url: str) -> Engine:
    url = make_url(database_url)
    if url.drivername.startswith("sqlite") and url.database and url.database != ":memory:":
        Path(url.database).parent.mkdir(parents=True, exist_ok=True)
    engine = create_engine(database_url, future=True)
    Base.metadata.create_all(engine)
    _migrate_sqlite_schema(engine)
    return engine


def _migrate_sqlite_schema(engine: Engine) -> None:
    """Apply additive MVP migrations for existing SQLite databases.

    `create_all()` intentionally does not alter an existing table. Keeping this
    small migration here avoids breaking a user's local M1 database when a new
    JSON metadata field is added.
    """
    if engine.dialect.name != "sqlite":
        return
    inspector = inspect(engine)
    if "papers" not in inspector.get_table_names():
        paper_columns = set()
    else:
        paper_columns = {column["name"] for column in inspector.get_columns("papers")}
    table_migrations = {
        "papers": {
            "metadata_sources": "JSON NOT NULL DEFAULT '[]'",
            "keywords": "JSON NOT NULL DEFAULT '[]'",
            "oa_locations": "JSON NOT NULL DEFAULT '[]'",
            "ranking_source": "VARCHAR(256)",
            "ranking_subject": "VARCHAR(512)",
            "journal_match_method": "VARCHAR(64)",
            "quality_accepted": "BOOLEAN",
            "quality_bucket": "VARCHAR(32)",
            "relevance_explanation": "TEXT",
        },
        "target_journals": {
            "issns": "JSON NOT NULL DEFAULT '[]'",
            "issn_l": "VARCHAR(16)",
            "aliases": "JSON NOT NULL DEFAULT '[]'",
        },
        "download_tasks": {
            "source": "VARCHAR(128)",
            "attempts": "INTEGER NOT NULL DEFAULT 0",
            "progress": "FLOAT NOT NULL DEFAULT 0.0",
        },
    }
    with engine.begin() as connection:
        for table, migrations in table_migrations.items():
            if table not in inspector.get_table_names():
                continue
            columns = (
                paper_columns
                if table == "papers"
                else {column["name"] for column in inspector.get_columns(table)}
            )
            for name, definition in migrations.items():
                if name not in columns:
                    connection.execute(
                        text(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
                    )
