from __future__ import annotations

import time
from datetime import date
from typing import Any

from clients.base import Transport
from clients.http import JSONClient
from core.cache import JsonFileCache
from models.domain import OpenAccessStatus, PaperRecord


class SemanticScholarClient(JSONClient):
    endpoint = "https://api.semanticscholar.org/graph/v1/paper/search"
    fields = (
        "paperId,externalIds,title,abstract,authors,year,publicationDate,"
        "venue,journal,openAccessPdf,citationCount,url"
    )

    def __init__(
        self,
        transport: Transport | None = None,
        *,
        api_key: str | None = None,
        timeout: float = 20,
        cache: JsonFileCache | None = None,
        max_retries: int = 3,
        sleep=None,
        min_request_interval_seconds: float = 1.1,
        clock=time.monotonic,
    ) -> None:
        kwargs: dict[str, Any] = {
            "transport": transport,
            "timeout": timeout,
            "cache": cache,
            "max_retries": max_retries,
            "min_request_interval_seconds": min_request_interval_seconds,
            "clock": clock,
        }
        if sleep is not None:
            kwargs["sleep"] = sleep
        super().__init__(**kwargs)
        self.api_key = api_key

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
        if not 1 <= per_page <= 100:
            raise ValueError("per_page must be between 1 and 100")
        if max_results < 1:
            raise ValueError("max_results must be positive")
        results: list[PaperRecord] = []
        offset = 0
        headers = {"Accept": "application/json"}
        if self.api_key:
            headers["x-api-key"] = self.api_key
        while len(results) < max_results:
            params: dict[str, Any] = {
                "query": query.strip(),
                "limit": min(per_page, max_results - len(results)),
                "offset": offset,
                "fields": self.fields,
            }
            if from_year is not None or to_year is not None:
                params["year"] = f"{from_year or '*'}-{to_year or '*'}"
            payload = self.get_json(
                self.endpoint,
                params,
                headers=headers,
                namespace="semantic_scholar",
                cache_key=f"{self.endpoint}?{sorted(params.items())}",
            )
            page = [self.normalize_paper(item) for item in payload.get("data", [])]
            results.extend(page)
            if not page or len(page) < params["limit"]:
                break
            offset += len(page)
            if payload.get("total") is not None and offset >= int(payload["total"]):
                break
        return results[:max_results]

    @staticmethod
    def normalize_paper(item: dict[str, Any]) -> PaperRecord:
        external = item.get("externalIds") or {}
        open_access_pdf = item.get("openAccessPdf") or {}
        publication_date = None
        if item.get("publicationDate"):
            try:
                publication_date = date.fromisoformat(item["publicationDate"])
            except ValueError:
                pass
        journal = item.get("journal") or {}
        venue = journal.get("name") or item.get("venue")
        external_ids = {
            key.lower(): str(value)
            for key, value in external.items()
            if value
        }
        external_ids["semantic_scholar"] = str(item.get("paperId") or "")
        doi = external.get("DOI")
        return PaperRecord(
            source_api="semantic_scholar",
            source_id=str(item.get("paperId") or ""),
            doi=doi,
            title=item.get("title") or "[untitled]",
            authors=[
                author.get("name")
                for author in item.get("authors", [])
                if author.get("name")
            ],
            abstract=item.get("abstract"),
            publication_year=item.get("year"),
            publication_date=publication_date,
            journal_name=venue,
            publisher=None,
            citation_count=item.get("citationCount"),
            open_access_status=(
                OpenAccessStatus.OPEN
                if open_access_pdf.get("url")
                else OpenAccessStatus.UNKNOWN
            ),
            pdf_url=open_access_pdf.get("url"),
            oa_locations=(
                [open_access_pdf["url"]]
                if open_access_pdf.get("url")
                else []
            ),
            landing_page_url=item.get("url"),
            external_ids=external_ids,
            metadata_sources=["semantic_scholar"],
        )
