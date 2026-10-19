from __future__ import annotations

from typing import Any

from clients.crossref import CrossrefClient


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


def work(doi: str, title: str) -> dict[str, Any]:
    return {
        "DOI": doi,
        "URL": "https://doi.org/" + doi,
        "title": [title],
        "author": [{"given": "Ada", "family": "Lovelace"}],
        "published-online": {"date-parts": [[2023, 5, 6]]},
        "container-title": ["Journal of Legal Technology"],
        "ISSN": ["1234-5678"],
        "publisher": "Example Publisher",
        "abstract": "<jats:p>Useful <jats:italic>abstract</jats:italic>.</jats:p>",
        "is-referenced-by-count": 9,
    }


def test_search_uses_cursor_pagination_and_does_not_claim_pdf() -> None:
    transport = Transport(
        [
            Response(
                {
                    "message": {
                        "items": [work("10.2000/one", "First")],
                        "next-cursor": "next",
                    }
                }
            ),
            Response(
                {
                    "message": {
                        "items": [work("10.2000/two", "Second")],
                        "next-cursor": "next2",
                    }
                }
            ),
        ]
    )
    client = CrossrefClient(transport, max_retries=0)
    papers = client.search("legal technology", per_page=1, max_results=2)
    assert [paper.doi for paper in papers] == ["10.2000/one", "10.2000/two"]
    assert transport.calls[1]["params"]["cursor"] == "next"
    assert papers[0].abstract == "Useful  abstract ."
    assert papers[0].pdf_url is None
