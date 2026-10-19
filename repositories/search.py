from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.db import Author, Paper, SearchResult, SearchSession
from models.domain import PaperRecord


class SearchRepository:
    """SQLite persistence for canonical papers and reproducible search runs."""

    def __init__(self, engine: Any) -> None:
        self.engine = engine

    def save_search(
        self,
        query: str,
        papers: list[PaperRecord],
        *,
        parameters: dict[str, Any] | None = None,
    ) -> int:
        with Session(self.engine) as session:
            search_session = SearchSession(
                query=query,
                parameters=parameters or {},
                created_at=datetime.utcnow(),
            )
            session.add(search_session)
            session.flush()
            for rank, record in enumerate(papers, start=1):
                paper = self._find_existing(session, record)
                if paper is None:
                    paper = Paper(
                        source_api=record.source_api,
                        source_id=record.source_id,
                    )
                    session.add(paper)
                self._apply_record(paper, record)
                session.flush()
                self._attach_authors(session, paper, record.authors)
                session.add(
                    SearchResult(
                        session_id=search_session.id,
                        paper_id=paper.id,
                        rank=rank,
                    )
                )
            session.commit()
            return int(search_session.id)

    @staticmethod
    def _find_existing(session: Session, record: PaperRecord) -> Paper | None:
        if record.doi:
            found = session.scalar(select(Paper).where(Paper.doi == record.doi))
            if found:
                return found
        found = session.scalar(
            select(Paper).where(
                Paper.source_api == record.source_api,
                Paper.source_id == record.source_id,
            )
        )
        if found:
            return found
        candidates = session.scalars(select(Paper).where(Paper.title == record.title)).all()
        compatible = [
            candidate
            for candidate in candidates
            if (candidate.doi is None or candidate.doi == record.doi)
            and (
                not candidate.publication_year
                or not record.publication_year
                or candidate.publication_year == record.publication_year
            )
        ]
        if len(compatible) == 1:
            return compatible[0]
        return None

    @staticmethod
    def _apply_record(paper: Paper, record: PaperRecord) -> None:
        paper.doi = record.doi or paper.doi
        paper.title = record.title
        paper.abstract = record.abstract or paper.abstract
        paper.keywords = list(dict.fromkeys([*(paper.keywords or []), *record.keywords]))
        paper.publication_year = record.publication_year or paper.publication_year
        paper.publication_date = record.publication_date or paper.publication_date
        paper.journal_name = record.journal_name or paper.journal_name
        paper.publisher = record.publisher or paper.publisher
        paper.source_api = paper.source_api or record.source_api
        paper.source_id = paper.source_id or record.source_id
        paper.external_ids = {**(paper.external_ids or {}), **record.external_ids}
        paper.metadata_sources = list(
            dict.fromkeys([*(paper.metadata_sources or []), *record.metadata_sources])
        )
        paper.issn = list(dict.fromkeys([*(paper.issn or []), *record.issn]))
        paper.citation_count = record.citation_count or paper.citation_count
        if record.quartile.value != "Unknown":
            paper.quartile = record.quartile.value
            paper.quartile_year = record.quartile_year or paper.quartile_year
            paper.ranking_source = record.ranking_source or paper.ranking_source
            paper.ranking_subject = record.ranking_subject or paper.ranking_subject
        if record.quality_accepted is not None:
            paper.whitelist_matched = record.whitelist_matched
            paper.journal_match_method = (
                record.journal_match_method or paper.journal_match_method
            )
            paper.matched_rule = record.matched_rule or paper.matched_rule
            paper.quality_accepted = record.quality_accepted
            paper.quality_bucket = record.quality_bucket or paper.quality_bucket
        paper.relevance_score = (
            record.relevance_score
            if record.relevance_score is not None
            else paper.relevance_score
        )
        paper.relevance_explanation = (
            record.relevance_explanation or paper.relevance_explanation
        )
        paper.open_access_status = (
            record.open_access_status.value
            if record.open_access_status.value != "unknown"
            else paper.open_access_status
        )
        paper.pdf_url = record.pdf_url or paper.pdf_url
        paper.oa_locations = list(
            dict.fromkeys([*(paper.oa_locations or []), *record.oa_locations])
        )
        paper.landing_page_url = record.landing_page_url or paper.landing_page_url

    @staticmethod
    def _attach_authors(session: Session, paper: Paper, author_names: list[str]) -> None:
        existing = {author.display_name: author for author in paper.authors}
        for name in author_names:
            author = existing.get(name)
            if author is None:
                author = session.scalar(select(Author).where(Author.display_name == name))
            if author is None:
                author = Author(display_name=name)
                session.add(author)
                session.flush()
            if author not in paper.authors:
                paper.authors.append(author)
