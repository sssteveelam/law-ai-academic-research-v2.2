from __future__ import annotations

import time
from datetime import date
from typing import Any

import httpx

from clients.base import Transport
from core.cache import JsonFileCache
from core.errors import ExternalAPIError
from models.domain import OpenAccessStatus, PaperRecord


class OpenAlexClient:
    endpoint = "https://api.openalex.org/works"

    def __init__(
        self,
        transport: Transport | None = None,
        *,
        email: str | None = None,
        api_key: str | None = None,
        timeout: float = 20,
        cache: JsonFileCache | None = None,
        max_retries: int = 3,
        sleep=time.sleep,
    ) -> None:
        self.transport = transport or httpx.Client()
        self.email = email
        self.api_key = api_key
        self.timeout = timeout
        self.cache = cache
        self.max_retries = max_retries
        self.sleep = sleep

    def search(
        self,
        query: str,
        *,
        per_page: int = 25,
        max_results: int = 100,
        from_year: int | None = None,
        to_year: int | None = None,
    ) -> list[PaperRecord]:
        if not query.strip():
            raise ValueError("query must not be empty")
        if not 1 <= per_page <= 200:
            raise ValueError("per_page must be between 1 and 200")
        if max_results < 1:
            raise ValueError("max_results must be positive")
        results: list[PaperRecord] = []
        cursor = "*"
        while len(results) < max_results:
            params: dict[str, Any] = {
                "search": query.strip(),
                "per-page": min(per_page, max_results - len(results)),
                "cursor": cursor,
            }
            filters = []
            if from_year is not None:
                filters.append(f"from_publication_date:{from_year}-01-01")
            if to_year is not None:
                filters.append(f"to_publication_date:{to_year}-12-31")
            if filters:
                params["filter"] = ",".join(filters)
            payload = self._get_json(params)
            page = [self.normalize_work(item) for item in payload.get("results", [])]
            results.extend(page)
            meta = payload.get("meta", {})
            next_cursor = meta.get("next_cursor")
            if not page or not next_cursor or next_cursor == cursor:
                break
            cursor = next_cursor
        return results[:max_results]

    def lookup_dois(self, dois: list[str]) -> dict[str, PaperRecord]:
        """Fetch existing works by DOI in batches, for legacy records without OA URLs.

        Returns only exact DOI matches: title-based guesses are unsafe for full text.
        The same caching, authentication, rate-limit and retry machinery as search
        is used. OpenAlex supports up to 100 DOI values in an OR filter.
        """
        normalized = list(dict.fromkeys(
            doi.strip().lower().removeprefix("https://doi.org/")
            for doi in dois if doi and doi.strip()
        ))
        works: dict[str, PaperRecord] = {}
        for start in range(0, len(normalized), 50):
            group = normalized[start:start + 50]
            wanted = set(group)
            payload = self._get_json({
                "filter": "doi:" + "|".join(f"https://doi.org/{doi}" for doi in group),
                "per_page": len(group),
            })
            for item in payload.get("results", []):
                if not isinstance(item, dict):
                    continue
                try:
                    paper = self.normalize_work(item)
                except (ValueError, TypeError):
                    continue
                if paper.doi in wanted:
                    works[paper.doi] = paper
        return works

    def _get_json(self, params: dict[str, Any]) -> dict[str, Any]:
        cache_key = f"{self.endpoint}?{sorted(params.items())}|email={self.email}"
        if self.cache:
            cached = self.cache.get("openalex", cache_key)
            if isinstance(cached, dict):
                return cached
        headers = {"Accept": "application/json"}
        request_params = dict(params)
        if self.email:
            request_params["mailto"] = self.email
        if self.api_key:
            request_params["api_key"] = self.api_key
        last_error: Exception | None = None
        for attempt in range(self.max_retries + 1):
            try:
                response = self.transport.get(
                    self.endpoint,
                    params=request_params,
                    headers=headers,
                    timeout=self.timeout,
                )
                status = response.status_code
                if status == 200:
                    payload = response.json()
                    if not isinstance(payload, dict):
                        raise ExternalAPIError("OpenAlex returned a non-object payload")
                    if self.cache:
                        self.cache.set("openalex", cache_key, payload)
                    return payload
                if status not in (429, 500, 502, 503, 504):
                    raise ExternalAPIError(f"OpenAlex HTTP {status}")
                retry_after = response.headers.get("Retry-After")
                delay = float(retry_after) if retry_after and retry_after.isdigit() else 2**attempt
                if attempt < self.max_retries:
                    self.sleep(delay)
                    continue
                raise ExternalAPIError(f"OpenAlex HTTP {status} after retries")
            except (httpx.TimeoutException, httpx.NetworkError) as exc:
                last_error = exc
                if attempt < self.max_retries:
                    self.sleep(2**attempt)
                    continue
                raise ExternalAPIError("OpenAlex request failed after retries") from exc
        raise ExternalAPIError("OpenAlex request failed") from last_error

    @staticmethod
    def normalize_work(work: dict[str, Any]) -> PaperRecord:
        primary_location = work.get("primary_location") or {}
        source = primary_location.get("source") or {}
        best_oa = work.get("best_oa_location") or {}
        open_access = work.get("open_access") or {}
        abstract = _decode_inverted_index(work.get("abstract_inverted_index"))
        publication_date = None
        raw_date = work.get("publication_date")
        if raw_date:
            try:
                publication_date = date.fromisoformat(raw_date)
            except ValueError:
                publication_date = None
        authors = [
            (authorship.get("author") or {}).get("display_name")
            for authorship in work.get("authorships", [])
        ]
        authors = [author for author in authors if author]
        keywords = [
            item.get("keyword")
            for item in work.get("keywords", [])
            if isinstance(item, dict) and item.get("keyword")
        ]
        keywords.extend(
            concept.get("display_name")
            for concept in work.get("concepts", [])
            if isinstance(concept, dict) and concept.get("display_name")
        )
        ids = work.get("ids") or {}
        doi = work.get("doi") or ids.get("doi")
        landing = primary_location.get("landing_page_url") or work.get("id")
        # OpenAlex Location objects use the top-level `pdf_url` string.
        # The older nested `pdf.url` shape is supported for legacy cached data.
        # `best_oa_location` denotes a vetted OA copy even if `is_oa` is omitted.
        pdf_url = (
            _location_pdf_url(best_oa)
            if best_oa.get("is_oa") is not False
            else None
        )
        if not pdf_url and primary_location.get("is_oa") is True:
            # Do not infer OA from a publisher link without the location OA flag.
            pdf_url = _location_pdf_url(primary_location)
        oa_locations = [
            url
            for location in work.get("locations", [])
            if isinstance(location, dict) and location.get("is_oa") is True
            if (url := _location_pdf_url(location)) is not None
        ]
        if pdf_url and pdf_url not in oa_locations:
            oa_locations.insert(0, pdf_url)
        return PaperRecord(
            source_api="openalex",
            source_id=str(work.get("id") or ids.get("openalex") or ""),
            doi=doi,
            title=work.get("title") or work.get("display_name") or "[untitled]",
            authors=authors,
            abstract=abstract,
            keywords=list(dict.fromkeys(keywords)),
            publication_year=work.get("publication_year"),
            publication_date=publication_date,
            journal_name=source.get("display_name"),
            issn=_unique_strings(
                [source.get("issn_l"), *(source.get("issn") or [])]
            ),
            publisher=(source.get("host_organization_name") or None),
            citation_count=work.get("cited_by_count"),
            open_access_status=(
                OpenAccessStatus.OPEN
                if open_access.get("is_oa") is True
                else OpenAccessStatus.CLOSED
                if open_access.get("is_oa") is False
                else OpenAccessStatus.UNKNOWN
            ),
            pdf_url=pdf_url,
            oa_locations=list(dict.fromkeys(oa_locations)),
            landing_page_url=landing,
            external_ids={key: str(value) for key, value in ids.items() if value},
            metadata_sources=["openalex"],
        )


def _decode_inverted_index(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    tokens: list[tuple[int, str]] = []
    for word, positions in value.items():
        if isinstance(positions, list):
            tokens.extend((position, word) for position in positions if isinstance(position, int))
    if not tokens:
        return None
    return " ".join(word for _, word in sorted(tokens))


def _unique_strings(values: list[Any]) -> list[str]:
    result: list[str] = []
    for value in values:
        if isinstance(value, str) and value.strip() and value not in result:
            result.append(value)
    return result


def _location_pdf_url(location: dict[str, Any]) -> str | None:
    """Read the official OpenAlex location pdf_url, retaining legacy support."""
    raw = location.get("pdf_url")
    if not isinstance(raw, str) or not raw.strip():
        nested = location.get("pdf")
        raw = nested.get("url") if isinstance(nested, dict) else None
    if not isinstance(raw, str):
        return None
    raw = raw.strip()
    from urllib.parse import urlparse
    parsed = urlparse(raw)
    return raw if parsed.scheme in {"http", "https"} and parsed.hostname else None
