from __future__ import annotations

from typing import Any

import httpx
import pytest

from clients.openalex import OpenAlexClient
from core.errors import ExternalAPIError


class FakeResponse:
    def __init__(
        self,
        payload: dict[str, Any],
        status_code: int = 200,
        headers: dict[str, str] | None = None,
    ):
        self.payload = payload
        self.status_code = status_code
        self.headers = headers or {}

    def json(self) -> dict[str, Any]:
        return self.payload


class FakeTransport:
    def __init__(self, responses: list[FakeResponse]):
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        self.calls.append({"url": url, **kwargs})
        return self.responses.pop(0)


def work(identifier: str, title: str) -> dict[str, Any]:
    return {
        "id": f"https://openalex.org/{identifier}",
        "doi": "https://doi.org/10.1000/example",
        "title": title,
        "publication_year": 2024,
        "publication_date": "2024-03-01",
        "abstract_inverted_index": {"Legal": [1], "AI": [0]},
        "authorships": [{"author": {"display_name": "Nguyen A"}}],
        "primary_location": {
            "landing_page_url": "https://example.test/article",
            "source": {
                "display_name": "Example Law Review",
                "issn_l": "1234-5678",
                "issn": ["1234-5678"],
                "host_organization_name": "Example Press",
            },
        },
        "best_oa_location": {"pdf": {"url": "https://example.test/article.pdf"}},
        "open_access": {"is_oa": True},
        "ids": {"openalex": f"https://openalex.org/{identifier}"},
        "cited_by_count": 7,
    }


def test_normalize_work_preserves_metadata_and_decodes_abstract() -> None:
    paper = OpenAlexClient.normalize_work(work("W1", "A paper"))
    assert paper.source_id.endswith("W1")
    assert paper.doi == "10.1000/example"
    assert paper.abstract == "AI Legal"
    assert paper.pdf_url.endswith(".pdf")
    assert paper.authors == ["Nguyen A"]
    assert paper.issn == ["1234-5678"]


def test_search_follows_cursor_and_retries_rate_limit() -> None:
    transport = FakeTransport(
        [
            FakeResponse({}, 429, {"Retry-After": "0"}),
            FakeResponse(
                {"results": [work("W1", "First")], "meta": {"next_cursor": "next"}}
            ),
            FakeResponse({"results": [work("W2", "Second")], "meta": {"next_cursor": None}}),
        ]
    )
    sleeps: list[float] = []
    client = OpenAlexClient(transport, max_retries=2, sleep=sleeps.append)
    papers = client.search("liability", per_page=1, max_results=2)
    assert [paper.title for paper in papers] == ["First", "Second"]
    assert sleeps == [0.0]
    assert len(transport.calls) == 3
    assert transport.calls[-1]["params"]["cursor"] == "next"


def test_search_uses_cache_without_second_request(tmp_path) -> None:
    from core.cache import JsonFileCache

    transport = FakeTransport(
        [FakeResponse({"results": [work("W1", "Cached")], "meta": {"next_cursor": None}})]
    )
    cache = JsonFileCache(tmp_path)
    client = OpenAlexClient(transport, cache=cache)
    assert client.search("cache", max_results=1)[0].title == "Cached"
    second = OpenAlexClient(FakeTransport([]), cache=cache)
    assert second.search("cache", max_results=1)[0].title == "Cached"


def test_search_raises_after_timeout_retries() -> None:
    class TimeoutTransport:
        def get(self, url: str, **kwargs: Any) -> FakeResponse:
            raise httpx.ReadTimeout("timed out")

    sleeps: list[float] = []
    client = OpenAlexClient(TimeoutTransport(), max_retries=2, sleep=sleeps.append)
    with pytest.raises(ExternalAPIError, match="after retries"):
        client.search("timeout", max_results=1)
    assert sleeps == [1, 2]
