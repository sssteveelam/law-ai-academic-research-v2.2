"""Regression tests for PDF retrieval from DOI-only legacy records."""

from pathlib import Path

import httpx

from clients.openalex import OpenAlexClient
from models.domain import DownloadStatus, PaperRecord
from services.fulltext.downloader import PDFDownloader
from services.fulltext.queue import DownloadQueue
from services.fulltext.resolver import FullTextResolver

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


def paper(doi: str) -> PaperRecord:
    return PaperRecord(
        source_api="crossref", source_id=doi, doi=doi,
        title="AI Legal Responsibility", pdf_url=None,
        landing_page_url=f"https://doi.org/{doi}",
    )


def openalex_work(doi: str, pdf_url: str | None) -> dict:
    location = {"pdf": {"url": pdf_url}} if pdf_url else {}
    return {
        "id": "https://openalex.org/W123",
        "doi": f"https://doi.org/{doi}",
        "title": "AI Legal Responsibility",
        "best_oa_location": location,
        "locations": [{"is_oa": True, "pdf": {"url": pdf_url}}] if pdf_url else [],
        "open_access": {"is_oa": bool(pdf_url)},
    }


def test_bulk_lookup_dois_uses_exact_doi_and_single_request():
    calls = []

    def handler(request):
        calls.append(request)
        return httpx.Response(200, json={"results": [
            openalex_work("10.1111/a", "https://repo.example/a.pdf"),
            openalex_work("10.1111/b", "https://repo.example/b.pdf"),
            openalex_work("10.other/unrequested", "https://repo.example/wrong.pdf"),
        ]})

    client = OpenAlexClient(transport=httpx.Client(transport=httpx.MockTransport(handler)))
    results = client.lookup_dois(["10.1111/a", "10.1111/b", "10.1111/a"])
    assert len(calls) == 1
    assert calls[0].url.params["filter"] == "doi:https://doi.org/10.1111/a|https://doi.org/10.1111/b"
    assert sorted(results) == ["10.1111/a", "10.1111/b"]
    assert results["10.1111/a"].pdf_url == "https://repo.example/a.pdf"


def test_doi_only_legacy_paper_can_download_via_openalex(tmp_path: Path):
    api_calls = []
    def metadata(request):
        api_calls.append(request)
        return httpx.Response(200, json={"results": [
            openalex_work("10.1111/a", "https://repo.example/a.pdf")
        ]})
    def pdf(request):
        assert str(request.url) == "https://repo.example/a.pdf"
        # Some repositories mislabel a PDF as text/plain.
        return httpx.Response(200, content=PDF, headers={"Content-Type": "text/plain"})

    resolver = FullTextResolver(openalex=OpenAlexClient(
        transport=httpx.Client(transport=httpx.MockTransport(metadata))))
    queue = DownloadQueue(
        resolver,
        PDFDownloader(client=httpx.Client(transport=httpx.MockTransport(pdf))),
    )
    report = queue.download([paper("10.1111/a")], tmp_path)
    assert report.success_count == 1
    assert report.items[0].source == "openalex"
    assert report.items[0].local_path.read_bytes() == PDF
    assert len(api_calls) == 1


def test_doi_only_paper_without_oa_is_honestly_restricted(tmp_path: Path):
    api = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"results": []})
    ))
    queue = DownloadQueue(
        FullTextResolver(openalex=OpenAlexClient(transport=api)),
        PDFDownloader(client=httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=PDF)
        ))),
    )
    report = queue.download([paper("10.1111/b")], tmp_path)
    assert report.items[0].status == DownloadStatus.ACCESS_RESTRICTED
    assert "No lawful OA PDF" in report.items[0].error
    assert list(tmp_path.glob("*.pdf")) == []


def test_permission_denied_candidate_is_access_restricted(tmp_path: Path):
    queue = DownloadQueue(
        FullTextResolver(),
        PDFDownloader(client=httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(403)
        ))),
        max_attempts=1,
    )
    record = paper("10.1111/c").model_copy(update={"pdf_url": "https://repo.example/c.pdf"})
    result = queue.download([record], tmp_path)
    assert result.items[0].status == DownloadStatus.ACCESS_RESTRICTED
    assert "HTTP 403" in result.items[0].error


def test_api_failure_does_not_crash_and_is_reported(tmp_path: Path):
    api = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(401)
    ))
    queue = DownloadQueue(
        FullTextResolver(openalex=OpenAlexClient(transport=api, max_retries=0)),
        PDFDownloader(client=httpx.Client(transport=httpx.MockTransport(
            lambda request: httpx.Response(200, content=PDF)
        ))),
    )
    report = queue.download([paper("10.1111/d")], tmp_path)
    assert report.items[0].status == DownloadStatus.ACCESS_RESTRICTED
    assert "OpenAlex lookup unavailable" in report.items[0].error


def test_deduplicates_metadata_and_oa_links(tmp_path: Path):
    pdf_url = "https://repo.example/a.pdf"
    record = paper("10.1111/a").model_copy(update={"pdf_url": pdf_url})
    calls = []
    queue = DownloadQueue(
        FullTextResolver(),
        PDFDownloader(client=httpx.Client(transport=httpx.MockTransport(
            lambda request: (calls.append(request), httpx.Response(200, content=PDF))[1]
        ))),
    )
    report = queue.download([record, record], tmp_path)
    assert report.success_count == 2
    assert len(calls) == 1


def test_openalex_closed_primary_location_is_not_a_lawful_pdf_candidate():
    work = openalex_work("10.1111/closed", None)
    work["primary_location"] = {
        "is_oa": False,
        "pdf": {"url": "https://publisher.example/paywalled.pdf"},
    }
    normalized = OpenAlexClient.normalize_work(work)
    assert normalized.pdf_url is None
    assert normalized.oa_locations == []


def test_openalex_doi_lookup_batches_to_50_items():
    counts = []
    def handler(request):
        counts.append(request.url.params["per_page"])
        return httpx.Response(200, json={"results": []})
    client = OpenAlexClient(transport=httpx.Client(transport=httpx.MockTransport(handler)))
    assert not client.lookup_dois([f"10.1000/{i}" for i in range(102)])
    assert counts == ["50", "50", "2"]
