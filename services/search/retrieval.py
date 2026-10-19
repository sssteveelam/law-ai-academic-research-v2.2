from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from models.domain import PaperRecord
from services.ranking.identifiers import normalize_journal_name
from services.search.normalization import deduplicate_papers


@dataclass(frozen=True)
class SearchReport:
    papers: list[PaperRecord]
    source_errors: dict[str, str]
    source_counts: dict[str, int]


def search_sources(
    clients: dict[str, object],
    query: str,
    *,
    max_results: int = 50,
    from_year: int | None = None,
    to_year: int | None = None,
    on_source_error: Callable[[Exception], None] | None = None,
) -> SearchReport:
    """Search every configured source, isolate failures, then deduplicate."""
    all_papers: list[PaperRecord] = []
    errors: dict[str, str] = {}
    counts: dict[str, int] = {}
    for source_name, client in clients.items():
        try:
            papers = client.search(
                query,
                max_results=max_results,
                from_year=from_year,
                to_year=to_year,
            )
            counts[source_name] = len(papers)
            all_papers.extend(papers)
        except Exception as exc:
            errors[source_name] = str(exc)
            counts[source_name] = 0
            if on_source_error:
                on_source_error(exc)
    return SearchReport(
        papers=deduplicate_papers(all_papers),
        source_errors=errors,
        source_counts=counts,
    )


def retrieve_openalex(
    client: object,
    query: str,
    *,
    max_results: int = 50,
    on_source_error: Callable[[Exception], None] | None = None,
) -> list[PaperRecord]:
    """Backward-compatible one-source helper."""
    report = search_sources(
        {"openalex": client},
        query,
        max_results=max_results,
        on_source_error=on_source_error,
    )
    return report.papers


def filter_papers_by_journals(
    papers: list[PaperRecord],
    journal_names: list[str] | tuple[str, ...] | set[str],
) -> list[PaperRecord]:
    """Keep only papers whose normalized journal name is selected."""
    selected = {
        normalize_journal_name(name)
        for name in journal_names
        if normalize_journal_name(name)
    }
    if not selected:
        return list(papers)
    return [
        paper
        for paper in papers
        if normalize_journal_name(paper.journal_name) in selected
    ]
