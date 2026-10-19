from __future__ import annotations

from typing import Any

from clients.semantic_scholar import SemanticScholarClient


class Response:
    def __init__(self, payload: dict[str, Any], status_code: int = 200):
        self.payload = payload
        self.status_code = status_code
        self.headers: dict[str, str] = {}

    def json(self) -> dict[str, Any]:
        return self.payload


class Transport:
    def __init__(self, responses: list[Response]):
        self.responses = responses
        self.calls: list[dict[str, Any]] = []

    def get(self, url: str, **kwargs: Any) -> Response:
        self.calls.append({"url": url, **kwargs})
        return self.responses.pop(0)


def item(identifier: str, title: str) -> dict[str, Any]:
    return {
        "paperId": identifier,
        "externalIds": {"DOI": "10.1000/shared"},
        "title": title,
        "abstract": "A legal abstract",
        "authors": [{"authorId": "A1", "name": "Author One"}],
        "year": 2024,
        "publicationDate": "2024-01-02",
        "journal": {"name": "Law Review"},
        "openAccessPdf": {"url": "https://example.test/paper.pdf", "status": "GREEN"},
        "citationCount": 4,
        "url": "https://semanticscholar.org/paper/" + identifier,
    }


def test_search_uses_offset_pagination_and_normalizes() -> None:
    transport = Transport(
        [
            Response({"data": [item("S1", "First")], "total": 2}),
            Response({"data": [item("S2", "Second")], "total": 2}),
        ]
    )
    client = SemanticScholarClient(
        transport,
        max_retries=0,
        min_request_interval_seconds=0,
    )
    papers = client.search("AI liability", per_page=1, max_results=2)
    assert [paper.title for paper in papers] == ["First", "Second"]
    assert transport.calls[1]["params"]["offset"] == 1
    assert papers[0].doi == "10.1000/shared"
    assert papers[0].pdf_url.endswith(".pdf")
    assert papers[0].metadata_sources == ["semantic_scholar"]


def test_api_key_header_and_rate_limit_are_applied() -> None:
    transport = Transport(
        [
            Response({"data": [item("S1", "First")], "total": 2}),
            Response({"data": [item("S2", "Second")], "total": 2}),
        ]
    )
    sleeps: list[float] = []
    client = SemanticScholarClient(
        transport,
        api_key="test-key",
        max_retries=0,
        sleep=sleeps.append,
        clock=lambda: 0.0,
    )

    client.search("AI liability", per_page=1, max_results=2)

    assert transport.calls[0]["headers"]["x-api-key"] == "test-key"
    assert sleeps == [1.1]
