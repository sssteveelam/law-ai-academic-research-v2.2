from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from models.db import DownloadedFile, Paper, SearchResult, SearchSession
from models.domain import PaperRecord


@dataclass(frozen=True)
class LibraryPaper:
    paper_id: int
    paper: PaperRecord


class LibraryRepository:
    def __init__(self, engine: Any) -> None:
        self.engine = engine

    def list_papers(
        self,
        *,
        query: str | None = None,
        quality_bucket: str | None = None,
        quartile: str | None = None,
        open_access_only: bool = False,
        sort_by: str = "relevance",
        limit: int = 500,
    ) -> list[LibraryPaper]:
        with Session(self.engine) as session:
            papers = list(session.scalars(select(Paper)).all())
            rows = [self._to_library_paper(paper) for paper in papers]
        query_text = (query or "").strip().lower()
        if query_text:
            rows = [
                row
                for row in rows
                if query_text
                in " ".join(
                    [
                        row.paper.title,
                        row.paper.abstract or "",
                        row.paper.journal_name or "",
                        " ".join(row.paper.authors),
                    ]
                ).lower()
            ]
        if quality_bucket:
            rows = [row for row in rows if row.paper.quality_bucket == quality_bucket]
        if quartile:
            rows = [row for row in rows if row.paper.quartile.value == quartile]
        if open_access_only:
            rows = [row for row in rows if row.paper.pdf_url or row.paper.oa_locations]
        if sort_by == "year":
            rows.sort(key=lambda row: row.paper.publication_year or 0, reverse=True)
        elif sort_by == "title":
            rows.sort(key=lambda row: row.paper.title.lower())
        else:
            rows.sort(
                key=lambda row: row.paper.relevance_score
                if row.paper.relevance_score is not None
                else -1,
                reverse=True,
            )
        return rows[: max(1, limit)]

    def get_session_papers(self, session_id: int) -> list[LibraryPaper]:
        with Session(self.engine) as session:
            rows = session.execute(
                select(SearchResult, Paper)
                .join(Paper, Paper.id == SearchResult.paper_id)
                .where(SearchResult.session_id == session_id)
                .order_by(SearchResult.rank)
            ).all()
            return [
                self._to_library_paper(paper)
                for _, paper in rows
            ]

    def metrics(self) -> dict[str, int]:
        with Session(self.engine) as session:
            return {
                "papers": session.scalar(select(func.count(Paper.id))) or 0,
                "q1": session.scalar(
                    select(func.count(Paper.id)).where(Paper.quartile == "Q1")
                )
                or 0,
                "q2": session.scalar(
                    select(func.count(Paper.id)).where(Paper.quartile == "Q2")
                )
                or 0,
                "q3": session.scalar(
                    select(func.count(Paper.id)).where(Paper.quartile == "Q3")
                )
                or 0,
                "q4": session.scalar(
                    select(func.count(Paper.id)).where(Paper.quartile == "Q4")
                )
                or 0,
                "whitelist": session.scalar(
                    select(func.count(Paper.id)).where(Paper.whitelist_matched.is_(True))
                )
                or 0,
                "oa": session.scalar(
                    select(func.count(Paper.id)).where(
                        (Paper.pdf_url.is_not(None)) | (Paper.oa_locations != [])
                    )
                )
                or 0,
                "downloaded": session.scalar(
                    select(func.count(DownloadedFile.id))
                )
                or 0,
                "sessions": session.scalar(select(func.count(SearchSession.id))) or 0,
            }

    def recent_sessions(self, limit: int = 10) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            sessions = session.scalars(
                select(SearchSession)
                .order_by(SearchSession.created_at.desc())
                .limit(limit)
            ).all()
            return [
                {
                    "id": item.id,
                    "query": item.query,
                    "created_at": item.created_at,
                    "parameters": item.parameters or {},
                }
                for item in sessions
            ]

    @staticmethod
    def _to_library_paper(paper: Paper) -> LibraryPaper:
        record = PaperRecord.model_validate(
            {
                "source_api": paper.source_api,
                "source_id": paper.source_id,
                "doi": paper.doi,
                "title": paper.title,
                "authors": [author.display_name for author in paper.authors],
                "abstract": paper.abstract,
                "keywords": paper.keywords or [],
                "publication_year": paper.publication_year,
                "publication_date": paper.publication_date,
                "journal_name": paper.journal_name,
                "issn": paper.issn or [],
                "publisher": paper.publisher,
                "citation_count": paper.citation_count,
                "open_access_status": paper.open_access_status or "unknown",
                "pdf_url": paper.pdf_url,
                "oa_locations": paper.oa_locations or [],
                "landing_page_url": paper.landing_page_url,
                "external_ids": paper.external_ids or {},
                "metadata_sources": paper.metadata_sources or [],
                "quartile": paper.quartile or "Unknown",
                "quartile_year": paper.quartile_year,
                "ranking_source": paper.ranking_source,
                "ranking_subject": paper.ranking_subject,
                "whitelist_matched": paper.whitelist_matched,
                "journal_match_method": paper.journal_match_method,
                "matched_rule": paper.matched_rule,
                "quality_accepted": paper.quality_accepted,
                "quality_bucket": paper.quality_bucket,
                "relevance_score": paper.relevance_score,
                "relevance_explanation": paper.relevance_explanation,
            }
        )
        return LibraryPaper(paper_id=paper.id, paper=record)
