import sqlite3

from sqlalchemy import inspect

from repositories.database import create_database_engine


def test_database_schema_creates_core_tables() -> None:
    engine = create_database_engine("sqlite:///:memory:")
    tables = set(inspect(engine).get_table_names())
    assert {"papers", "authors", "journals", "journal_rankings", "keyword_presets"} <= tables


def test_existing_sqlite_database_gets_metadata_sources_migration(tmp_path) -> None:
    database_path = tmp_path / "legacy.db"
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            """
            CREATE TABLE papers (
                id INTEGER PRIMARY KEY,
                doi VARCHAR(512),
                title TEXT NOT NULL,
                source_api VARCHAR(64) NOT NULL,
                source_id VARCHAR(512) NOT NULL
            )
            """
        )
        connection.execute(
            "INSERT INTO papers (doi, title, source_api, source_id) "
            "VALUES (?, ?, ?, ?)",
            ("10.1/legacy", "Legacy paper", "legacy", "1"),
        )
        connection.commit()

    engine = create_database_engine(f"sqlite:///{database_path}")
    columns = {column["name"] for column in inspect(engine).get_columns("papers")}
    assert "metadata_sources" in columns
    assert "quality_bucket" in columns
    assert "oa_locations" in columns
    target_columns = {
        column["name"] for column in inspect(engine).get_columns("target_journals")
    }
    assert {"issns", "issn_l", "aliases"} <= target_columns
    download_columns = {
        column["name"] for column in inspect(engine).get_columns("download_tasks")
    }
    assert {"source", "attempts", "progress"} <= download_columns
