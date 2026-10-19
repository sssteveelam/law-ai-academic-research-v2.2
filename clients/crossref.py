from __future__ import annotations

import re
from datetime import date
from typing import Any

from clients.base import Transport
from clients.http import JSONClient
from core.cache import JsonFileCache
from models.domain import PaperRecord


class CrossrefClient(JSONClient):
    endpoint = "https://api.crossref.org/works"

    def __init__(
        self,
        transport: Transport | None = None,
        *,
        mailto: str | None = None,
        timeout: float = 20,
        cache: JsonFileCache | None = None,
        max_retries: int = 3,
        sleep=None,
    ) -> None:
        kwargs: dict[str, Any] = {
            "transport": transport,
            "timeout": timeout,
            "cache": cache,
            "max_retries": max_retries,
        }
        if sleep is not None:
            kwargs["sleep"] = sleep
        super().__init__(**kwargs)
        self.mailto = mailto

    def search(
        self,
        query: str,
        *,
        per_page: int = 100,
        max_results: int = 100,
        from_year: int | None = None,
        to_year: int | None = None,
    ) -> list[PaperRecord]:
        if not query.strip():
            raise ValueError("query must not be empty")
        if not 1 <= per_page <= 1000:
            raise ValueError("per_page must be between 1 and 1000")
        if max_results < 1:
            raise ValueError("max_results must be positive")
        results: list[PaperRecord] = []
        cursor = "*"
        headers = {"Accept": "application/json"}
        if self.mailto:
            headers["User-Agent"] = f"law-ai-academic-research/0.1 (mailto:{self.mailto})"
        while len(results) < max_results:
            params: dict[str, Any] = {
                "query.bibliographic": query.strip(),
                "rows": min(per_page, max_results - len(results)),
                "cursor": cursor,
            }
            if self.mailto:
                params["mailto"] = self.mailto
            if from_year is not None:
                params["filter"] = f"from-pub-date:{from_year}-01-01"
            if to_year is not None:
                suffix = f"until-pub-date:{to_year}-12-31"
                params["filter"] = f"{params.get('filter', '')},{suffix}".lstrip(",")
            payload = self.get_json(
                self.endpoint,
                params,
                headers=headers,
                namespace="crossref",
                cache_key=f"{self.endpoint}?{sorted(params.items())}",
            )
            message = payload.get("message") or {}
            page = [self.normalize_work(item) for item in message.get("items", [])]
            results.extend(page)
            next_cursor = message.get("next-cursor")
            if not page or not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
        return results[:max_results]

    @staticmethod
    def normalize_work(item: dict[str, Any]) -> PaperRecord:
        dates = (
            item.get("published-print")
            or item.get("published-online")
            or item.get("issued")
            or {}
        ).get("date-parts", [[]])
        parts = dates[0] if dates else []
        publication_date = None
        if parts:
            try:
                publication_date = date(
                    int(parts[0]),
                    int(parts[1]) if len(parts) > 1 else 1,
                    int(parts[2]) if len(parts) > 2 else 1,
                )
            except ValueError:
                pass
        doi = item.get("DOI")
        external_ids = {"crossref": str(item.get("URL") or doi or "")}
        if doi:
            external_ids["doi"] = str(doi)
        abstract = _strip_markup(item.get("abstract"))
        authors = [
            " ".join(part for part in (author.get("given"), author.get("family")) if part)
            for author in item.get("author", [])
        ]
        authors = [author for author in authors if author]
        return PaperRecord(
            source_api="crossref",
            source_id=str(doi or item.get("URL") or item.get("title", [""])[0]),
            doi=doi,
            title=(item.get("title") or ["[untitled]"])[0],
            authors=authors,
            abstract=abstract,
            keywords=[str(value) for value in (item.get("subject") or []) if value],
            publication_year=int(parts[0]) if parts else None,
            publication_date=publication_date,
            journal_name=(item.get("container-title") or [None])[0],
            issn=list(dict.fromkeys(item.get("ISSN") or [])),
            publisher=item.get("publisher"),
            citation_count=item.get("is-referenced-by-count"),
            landing_page_url=item.get("URL"),
            external_ids=external_ids,
            metadata_sources=["crossref"],
        )


def _strip_markup(value: str | None) -> str | None:
    if not value:
        return None
    return re.sub(r"<[^>]+>", " ", value).strip() or None
