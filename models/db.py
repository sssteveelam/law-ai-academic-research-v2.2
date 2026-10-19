from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Paper(Base):
    __tablename__ = "papers"

    id: Mapped[int] = mapped_column(primary_key=True)
    doi: Mapped[str | None] = mapped_column(String(512), unique=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    abstract: Mapped[str | None] = mapped_column(Text)
    keywords: Mapped[list] = mapped_column(JSON, default=list)
    publication_year: Mapped[int | None] = mapped_column(Integer)
    publication_date: Mapped[datetime | None] = mapped_column(Date)
    journal_name: Mapped[str | None] = mapped_column(String(512))
    publisher: Mapped[str | None] = mapped_column(String(512))
    source_api: Mapped[str] = mapped_column(String(64), nullable=False)
    source_id: Mapped[str] = mapped_column(String(512), nullable=False)
    external_ids: Mapped[dict] = mapped_column(JSON, default=dict)
    metadata_sources: Mapped[list] = mapped_column(JSON, default=list)
    issn: Mapped[list] = mapped_column(JSON, default=list)
    quartile: Mapped[str | None] = mapped_column(String(16))
    quartile_year: Mapped[int | None] = mapped_column(Integer)
    ranking_source: Mapped[str | None] = mapped_column(String(256))
    ranking_subject: Mapped[str | None] = mapped_column(String(512))
    whitelist_matched: Mapped[bool] = mapped_column(Boolean, default=False)
    journal_match_method: Mapped[str | None] = mapped_column(String(64))
    matched_rule: Mapped[str | None] = mapped_column(String(64))
    quality_accepted: Mapped[bool | None] = mapped_column(Boolean)
    quality_bucket: Mapped[str | None] = mapped_column(String(32))
    relevance_score: Mapped[float | None]
    relevance_explanation: Mapped[str | None] = mapped_column(Text)
    citation_count: Mapped[int | None] = mapped_column(Integer)
    open_access_status: Mapped[str | None] = mapped_column(String(32))
    pdf_url: Mapped[str | None] = mapped_column(String(2048))
    oa_locations: Mapped[list] = mapped_column(JSON, default=list)
    landing_page_url: Mapped[str | None] = mapped_column(String(2048))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, default=datetime.utcnow, onupdate=datetime.utcnow
    )

    authors: Mapped[list[Author]] = relationship(
        secondary="paper_authors", back_populates="papers"
    )


class Author(Base):
    __tablename__ = "authors"

    id: Mapped[int] = mapped_column(primary_key=True)
    display_name: Mapped[str] = mapped_column(String(512), nullable=False)
    external_ids: Mapped[dict] = mapped_column(JSON, default=dict)
    papers: Mapped[list[Paper]] = relationship(secondary="paper_authors", back_populates="authors")


class PaperAuthor(Base):
    __tablename__ = "paper_authors"

    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"), primary_key=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("authors.id"), primary_key=True)
    author_position: Mapped[int | None] = mapped_column(Integer)


class Journal(Base):
    __tablename__ = "journals"

    id: Mapped[int] = mapped_column(primary_key=True)
    canonical_name: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    issn_l: Mapped[str | None] = mapped_column(String(32))
    issns: Mapped[list] = mapped_column(JSON, default=list)
    publisher: Mapped[str | None] = mapped_column(String(512))


class SearchSession(Base):
    __tablename__ = "search_sessions"

    id: Mapped[int] = mapped_column(primary_key=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SearchResult(Base):
    __tablename__ = "search_results"

    session_id: Mapped[int] = mapped_column(ForeignKey("search_sessions.id"), primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"), primary_key=True)
    rank: Mapped[int | None] = mapped_column(Integer)


class TargetJournal(Base):
    __tablename__ = "target_journals"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(512), nullable=False)
    normalized_name: Mapped[str] = mapped_column(String(512), nullable=False, unique=True)
    group_name: Mapped[str | None] = mapped_column(String(256))
    issns: Mapped[list] = mapped_column(JSON, default=list)
    issn_l: Mapped[str | None] = mapped_column(String(16))
    aliases: Mapped[list] = mapped_column(JSON, default=list)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str | None] = mapped_column(String(512))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class JournalRanking(Base):
    __tablename__ = "journal_rankings"
    __table_args__ = (
        UniqueConstraint("issn", "ranking_year", "subject", "source"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    issn: Mapped[str | None] = mapped_column(String(32))
    journal_name: Mapped[str] = mapped_column(String(512), nullable=False)
    quartile: Mapped[str | None] = mapped_column(String(16))
    ranking_year: Mapped[int | None] = mapped_column(Integer)
    subject: Mapped[str | None] = mapped_column(String(256))
    source: Mapped[str] = mapped_column(String(256), nullable=False)


class DownloadTask(Base):
    __tablename__ = "download_tasks"

    id: Mapped[int] = mapped_column(primary_key=True)
    paper_id: Mapped[int] = mapped_column(ForeignKey("papers.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False)
    source_url: Mapped[str | None] = mapped_column(String(2048))
    source: Mapped[str | None] = mapped_column(String(128))
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    progress: Mapped[float] = mapped_column(default=0.0)
    error_message: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DownloadedFile(Base):
    __tablename__ = "downloaded_files"

    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("download_tasks.id"), nullable=False)
    local_path: Mapped[str] = mapped_column(String(2048), nullable=False)
    sha256: Mapped[str | None] = mapped_column(String(64))
    size_bytes: Mapped[int | None] = mapped_column(Integer)


class KeywordPreset(Base):
    __tablename__ = "keyword_presets"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    keywords: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
