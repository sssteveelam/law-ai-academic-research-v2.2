from __future__ import annotations

import zipfile
from pathlib import Path

import httpx
import pytest

from clients.unpaywall import UnpaywallClient
from models.domain import DownloadStatus, PaperRecord
from services.fulltext.downloader import (
    DownloadFailure,
    PDFDownloader,
)
from services.fulltext.queue import DownloadQueue, export_zip
from services.fulltext.resolver import FullTextResolver
from services.fulltext.security import UnsafeURL, validate_public_http_url

PDF = b"%PDF-1.7\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


def paper(title: str, url: str | None = None) -> PaperRecord:
    return PaperRecord(
        source_api="test",
        source_id=title,
        doi="10.1000/" + title.replace(" ", "-").lower(),
        title=title,
        pdf_url=url,
        metadata_sources=["openalex"] if url else [],
        landing_page_url="https://publisher.example/" + title.replace(" ", "-"),
    )


def client_for(handler):
    return httpx.Client(
        transport=httpx.MockTransport(handler),
        follow_redirects=True,
    )


def test_resolver_uses_direct_oa_then_unpaywall_and_keeps_restricted_landing() -> None:
    direct = FullTextResolver().resolve(
        paper("Direct", "https://repository.example/direct.pdf")
    )
    assert direct.status is DownloadStatus.OA_FOUND
    assert direct.candidate is not None
    assert direct.candidate.source == "openalex"

    def unpaywall_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "best_oa_location": {
                    "url_for_pdf": "https://repository.example/unpaywall.pdf",
                    "url": "https://repository.example/landing",
                }
            },
            request=request,
        )

    unpaywall = UnpaywallClient(
        httpx.Client(transport=httpx.MockTransport(unpaywall_handler)),
        email="researcher@example.org",
        max_retries=0,
    )
    resolved = FullTextResolver(unpaywall).resolve(paper("Unpaywall"))
    assert resolved.candidate is not None
    assert resolved.candidate.source == "unpaywall"

    restricted = FullTextResolver().resolve(paper("Restricted"))
    assert restricted.status is DownloadStatus.ACCESS_RESTRICTED
    assert restricted.candidate is None


def test_valid_pdf_is_downloaded_and_html_is_rejected(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("valid.pdf"):
            return httpx.Response(
                200,
                content=PDF,
                headers={"content-type": "application/pdf"},
                request=request,
            )
        return httpx.Response(
            200,
            content=b"<html>login</html>",
            headers={"content-type": "text/html"},
            request=request,
        )

    downloader = PDFDownloader(client=client_for(handler), max_bytes=1000)
    artifact = downloader.download(
        "https://repository.example/valid.pdf", tmp_path / "valid.pdf"
    )
    assert artifact.path.read_bytes().startswith(b"%PDF-")
    assert artifact.size_bytes == len(PDF)
    with pytest.raises(DownloadFailure) as exc_info:
        downloader.download(
            "https://repository.example/fake.pdf", tmp_path / "fake.pdf"
        )
    assert exc_info.value.invalid_pdf is True


@pytest.mark.parametrize("status", [403, 404])
def test_forbidden_and_missing_are_failed(status: int, tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, request=request)

    downloader = PDFDownloader(client=client_for(handler))
    with pytest.raises(DownloadFailure) as exc_info:
        downloader.download(
            f"https://repository.example/{status}.pdf",
            tmp_path / f"{status}.pdf",
        )
    assert exc_info.value.retryable is False


def test_retry_succeeds_after_transient_server_error(tmp_path: Path) -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        if calls == 1:
            return httpx.Response(503, request=request)
        return httpx.Response(
            200,
            content=PDF,
            headers={"content-type": "application/pdf"},
            request=request,
        )

    queue = DownloadQueue(
        FullTextResolver(),
        PDFDownloader(client=client_for(handler)),
        max_attempts=2,
    )
    result = queue.download(
        [paper("Retry", "https://repository.example/retry.pdf")],
        tmp_path,
    )
    assert result.success_count == 1
    assert result.items[0].attempts == 2


def test_batch_continues_after_one_failure_and_exports_only_valid_pdfs(tmp_path: Path) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("good.pdf"):
            return httpx.Response(
                200,
                content=PDF,
                headers={"content-type": "application/pdf"},
                request=request,
            )
        raise httpx.ConnectError("connection refused", request=request)

    progress = []
    queue = DownloadQueue(
        FullTextResolver(),
        PDFDownloader(client=client_for(handler)),
        max_attempts=1,
    )
    report = queue.download(
        [
            paper("Good", "https://repository.example/good.pdf"),
            paper("Broken", "https://repository.example/broken.pdf"),
        ],
        tmp_path / "pdfs",
        progress_callback=progress.append,
    )
    assert report.success_count == 1
    assert report.failure_count == 1
    assert report.success_rate == 0.5
    assert [entry.completed for entry in progress] == [1, 2]

    zip_path = export_zip(report, tmp_path / "downloaded.zip")
    with zipfile.ZipFile(zip_path) as archive:
        assert archive.namelist() == ["Good.pdf"]


def test_queue_falls_back_to_second_pdf_candidate(tmp_path: Path) -> None:
    class Resolver:
        def resolve(self, current_paper: PaperRecord):
            from services.fulltext.resolver import (
                FullTextCandidate,
                FullTextResolution,
            )

            return FullTextResolution(
                status=DownloadStatus.OA_FOUND,
                candidate=FullTextCandidate(
                    "https://repository.example/blocked.pdf",
                    "unpaywall",
                    True,
                ),
                landing_page_url=current_paper.landing_page_url,
                candidates=(
                    FullTextCandidate(
                        "https://repository.example/blocked.pdf",
                        "unpaywall",
                        True,
                    ),
                    FullTextCandidate(
                        "https://repository.example/backup.pdf",
                        "repository",
                        True,
                    ),
                ),
                reason="lawful open-access candidate found",
            )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("blocked.pdf"):
            return httpx.Response(403, request=request)
        return httpx.Response(
            200,
            content=PDF,
            headers={"content-type": "application/pdf"},
            request=request,
        )

    queue = DownloadQueue(
        Resolver(),
        PDFDownloader(client=client_for(handler)),
        max_attempts=1,
    )
    result = queue.download([paper("Fallback")], tmp_path)

    assert result.success_count == 1
    assert result.items[0].source == "repository"
    assert result.items[0].attempts == 1


def test_retry_failed_reprocesses_only_failed_items(tmp_path: Path) -> None:
    attempts = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise httpx.ConnectError("temporary", request=request)
        return httpx.Response(
            200,
            content=PDF,
            headers={"content-type": "application/pdf"},
            request=request,
        )

    queue = DownloadQueue(
        FullTextResolver(),
        PDFDownloader(client=client_for(handler)),
        max_attempts=1,
    )
    first = queue.download(
        [paper("Retry later", "https://repository.example/retry-later.pdf")],
        tmp_path,
    )
    assert first.failure_count == 1
    second = queue.retry_failed(first, tmp_path)
    assert second.success_count == 1


def test_retry_failed_includes_access_restricted_items(tmp_path: Path) -> None:
    class RetryResolver:
        def __init__(self) -> None:
            self.calls = 0

        def resolve(self, current_paper: PaperRecord):
            self.calls += 1
            if self.calls == 1:
                return FullTextResolver().resolve(current_paper)
            return FullTextResolver().resolve(
                current_paper.model_copy(update={"pdf_url": "https://repository.example/retry.pdf"})
            )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            content=PDF,
            headers={"content-type": "application/pdf"},
            request=request,
        )

    resolver = RetryResolver()
    queue = DownloadQueue(
        resolver,
        PDFDownloader(client=client_for(handler)),
        max_attempts=1,
    )
    first = queue.download([paper("Restricted first")], tmp_path)
    assert first.items[0].status is DownloadStatus.ACCESS_RESTRICTED
    second = queue.retry_failed(first, tmp_path)
    assert second.success_count == 1


def test_ssrf_urls_are_rejected() -> None:
    with pytest.raises(UnsafeURL):
        validate_public_http_url("http://127.0.0.1/private.pdf")
    with pytest.raises(UnsafeURL):
        validate_public_http_url("http://localhost/private.pdf")
