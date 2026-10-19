from __future__ import annotations

from datetime import date
from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field, field_validator


class Quartile(StrEnum):
    Q1 = "Q1"
    Q2 = "Q2"
    Q3 = "Q3"
    Q4 = "Q4"
    UNRANKED = "Unranked"
    UNKNOWN = "Unknown"


class OpenAccessStatus(StrEnum):
    OPEN = "open"
    CLOSED = "closed"
    UNKNOWN = "unknown"


class DownloadStatus(StrEnum):
    NOT_CHECKED = "NOT_CHECKED"
    OA_FOUND = "OA_FOUND"
    ACCESS_RESTRICTED = "ACCESS_RESTRICTED"
    DOWNLOAD_PENDING = "DOWNLOAD_PENDING"
    DOWNLOADING = "DOWNLOADING"
    DOWNLOADED = "DOWNLOADED"
    FAILED = "FAILED"
    INVALID_PDF = "INVALID_PDF"


class PaperRecord(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_api: str
    source_id: str
    doi: str | None = None
    title: str
    authors: list[str] = Field(default_factory=list)
    abstract: str | None = None
    keywords: list[str] = Field(default_factory=list)
    publication_year: int | None = None
    publication_date: date | None = None
    journal_name: str | None = None
    issn: list[str] = Field(default_factory=list)
    publisher: str | None = None
    citation_count: int | None = None
    open_access_status: OpenAccessStatus = OpenAccessStatus.UNKNOWN
    pdf_url: str | None = None
    oa_locations: list[str] = Field(default_factory=list)
    landing_page_url: str | None = None
    external_ids: dict[str, str] = Field(default_factory=dict)
    metadata_sources: list[str] = Field(default_factory=list)
    quartile: Quartile = Quartile.UNKNOWN
    quartile_year: int | None = None
    ranking_source: str | None = None
    ranking_subject: str | None = None
    whitelist_matched: bool = False
    journal_match_method: str | None = None
    matched_rule: str | None = None
    quality_accepted: bool | None = None
    quality_bucket: str | None = None
    relevance_score: float | None = Field(default=None, ge=0, le=1)
    relevance_explanation: str | None = None

    @field_validator("doi", mode="before")
    @classmethod
    def normalize_doi(cls, value: str | None) -> str | None:
        if not value:
            return None
        cleaned = value.strip().lower()
        for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix) :]
        return cleaned or None

    @field_validator("title")
    @classmethod
    def require_title(cls, value: str) -> str:
        title = " ".join(value.split())
        if not title:
            raise ValueError("title must not be empty")
        return title
