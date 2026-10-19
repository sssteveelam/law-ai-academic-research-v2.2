"""Regression tests for the official OpenAlex 2026 location.pdf_url schema."""

from pathlib import Path

import httpx

from clients.openalex import OpenAlexClient
from models.domain import DownloadStatus, PaperRecord
from services.fulltext.downloader import PDFDownloader
from services.fulltext.queue import DownloadQueue
from services.fulltext.resolver import FullTextResolver

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


def work(doi: str, *, primary_oa: bool = False) -> dict:
    return {
        "id": "https://openalex.org/W120",
        "doi": f"https://doi.org/{doi}",
        "title": "A Law and AI Research Paper",
        "open_access": {"is_oa": True},
        "best_oa_location": {
            "is_oa": True,
            "pdf_url": "https://repo.example/accepted.pdf",
            "landing_page_url": "https://repo.example/entry",
        },
        "primary_location": {
            "is_oa": primary_oa,
            "pdf_url": "https://publisher.example/record.pdf",
            "landing_page_url": f"https://doi.org/{doi}",
        },
        "locations": [
            {"is_oa": False, "pdf_url": "https://publisher.example/paywalled.pdf"},
            {"is_oa": True, "pdf_url": "https://repo.example/accepted.pdf"},
            {"is_oa": True, "pdf_url": "https://repo.example/mirror.pdf"},
        ],
    }


def record(doi: str, *, pdf_url: str | None = None) -> PaperRecord:
    return PaperRecord(
        source_api="crossref", source_id=doi, doi=doi,
        title="A Law and AI Research Paper", pdf_url=pdf_url,
        landing_page_url=f"https://doi.org/{doi}",
    )


def test_official_openalex_pdf_url_is_detected_and_paywall_excluded():
    parsed = OpenAlexClient.normalize_work(work("10.9876/test"))
    assert parsed.pdf_url == "https://repo.example/accepted.pdf"
    assert parsed.oa_locations == [
        "https://repo.example/accepted.pdf", "https://repo.example/mirror.pdf"
    ]
    assert "https://publisher.example/paywalled.pdf" not in parsed.oa_locations


def test_openalex_primary_location_only_when_flagged_oa():
    raw = work("10.9876/test", primary_oa=True)
    raw["best_oa_location"] = None
    raw["locations"] = []
    parsed = OpenAlexClient.normalize_work(raw)
    assert parsed.pdf_url == "https://publisher.example/record.pdf"

    raw["primary_location"]["is_oa"] = False
    assert OpenAlexClient.normalize_work(raw).pdf_url is None


def test_download_falls_back_to_new_location_when_existing_url_is_stale(tmp_path: Path):
    doi = "10.9876/test"
    calls: list[str] = []

    def meta_handler(request: httpx.Request) -> httpx.Response:
        calls.append("openalex")
        return httpx.Response(200, json={"results": [work(doi)]})

    def pdf_handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if str(request.url) == "https://publisher.example/stale.pdf":
            return httpx.Response(403)
        if str(request.url) == "https://repo.example/accepted.pdf":
            return httpx.Response(200, content=PDF, headers={"Content-Type": "application/pdf"})
        return httpx.Response(404)

    queue = DownloadQueue(
        FullTextResolver(openalex=OpenAlexClient(
            transport=httpx.Client(transport=httpx.MockTransport(meta_handler))
        )),
        PDFDownloader(client=httpx.Client(transport=httpx.MockTransport(pdf_handler))),
        max_attempts=1,
    )
    report = queue.download([record(doi, pdf_url="https://publisher.example/stale.pdf")], tmp_path)
    assert report.success_count == 1
    assert report.items[0].status == DownloadStatus.DOWNLOADED
    assert report.items[0].source == "openalex"
    assert report.items[0].local_path.read_bytes() == PDF
    assert calls == ["openalex", "https://publisher.example/stale.pdf", "https://repo.example/accepted.pdf"]


def test_unpaywall_outage_is_not_silently_labeled_as_no_oa():
    class UnavailableUnpaywall:
        def lookup(self, _doi):
            raise RuntimeError("Do not log confidential endpoint details")

    resolver = FullTextResolver(unpaywall=UnavailableUnpaywall())
    result = resolver.resolve(record("10.9876/test"))
    assert result.status == DownloadStatus.ACCESS_RESTRICTED
    assert "Unpaywall lookup unavailable (RuntimeError)" in result.reason
    assert "confidential" not in result.reason
