from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from models.domain import DownloadStatus, PaperRecord
from services.fulltext.downloader import (
    DownloadedArtifact,
    DownloadFailure,
    PDFDownloader,
    safe_filename,
)
from services.fulltext.resolver import FullTextResolver


@dataclass
class DownloadItemResult:
    paper: PaperRecord
    status: DownloadStatus
    source_url: str | None = None
    source: str | None = None
    local_path: Path | None = None
    sha256: str | None = None
    size_bytes: int | None = None
    attempts: int = 0
    error: str | None = None


@dataclass(frozen=True)
class DownloadProgress:
    completed: int
    total: int
    current_title: str
    successes: int
    failures: int


@dataclass
class BatchDownloadReport:
    items: list[DownloadItemResult] = field(default_factory=list)

    @property
    def downloaded(self) -> list[DownloadItemResult]:
        return [item for item in self.items if item.status is DownloadStatus.DOWNLOADED]

    @property
    def success_count(self) -> int:
        return len(self.downloaded)

    @property
    def failure_count(self) -> int:
        return len(
            [
                item
                for item in self.items
                if item.status
                in {
                    DownloadStatus.FAILED,
                    DownloadStatus.INVALID_PDF,
                    DownloadStatus.ACCESS_RESTRICTED,
                }
            ]
        )

    @property
    def success_rate(self) -> float:
        return self.success_count / len(self.items) if self.items else 0.0


class DownloadQueue:
    def __init__(
        self,
        resolver: FullTextResolver,
        downloader: PDFDownloader,
        *,
        max_attempts: int = 3,
    ) -> None:
        self.resolver = resolver
        self.downloader = downloader
        self.max_attempts = max(1, max_attempts)

    def download(
        self,
        papers: list[PaperRecord],
        output_dir: Path,
        *,
        progress_callback: Callable[[DownloadProgress], None] | None = None,
    ) -> BatchDownloadReport:
        report = BatchDownloadReport()
        total = len(papers)
        seen_urls: dict[str, DownloadedArtifact] = {}
        seen_hashes: dict[str, Path] = {}
        # Refresh PDF links for old Crossref-only records before attempting downloads.
        prime = getattr(self.resolver, "prime", None)
        if callable(prime):
            prime(papers)
        for completed, paper in enumerate(papers, start=1):
            resolution = self.resolver.resolve(paper)
            if not resolution.candidate:
                item = DownloadItemResult(
                    paper=paper,
                    status=resolution.status,
                    source_url=resolution.landing_page_url,
                    error=resolution.reason,
                )
                report.items.append(item)
                self._progress(report, completed, total, paper.title, progress_callback)
                continue
            item: DownloadItemResult | None = None
            for candidate in resolution.candidates:
                if candidate.url in seen_urls:
                    artifact = seen_urls[candidate.url]
                    item = DownloadItemResult(
                        paper=paper,
                        status=DownloadStatus.DOWNLOADED,
                        source_url=candidate.url,
                        source=candidate.source,
                        local_path=artifact.path,
                        sha256=artifact.sha256,
                        size_bytes=artifact.size_bytes,
                        attempts=0,
                    )
                    break
                candidate_result = self._download_one(
                    paper,
                    candidate.url,
                    candidate.source,
                    output_dir,
                    seen_hashes,
                )
                item = candidate_result
                if item.status is DownloadStatus.DOWNLOADED:
                    seen_urls[candidate.url] = DownloadedArtifact(
                        item.local_path,
                        item.source_url or candidate.url,
                        item.sha256 or "",
                        item.size_bytes or 0,
                        "application/pdf",
                    )
                    break
            if item is None:
                item = DownloadItemResult(
                    paper=paper,
                    status=resolution.status,
                    source_url=resolution.landing_page_url,
                    error=resolution.reason,
                )
            elif item.status is not DownloadStatus.DOWNLOADED and len(resolution.candidates) > 1:
                item.error = (
                    f"all {len(resolution.candidates)} PDF candidates failed; "
                    f"last error: {item.error or 'download failed'}"
                )
            report.items.append(item)
            self._progress(report, completed, total, paper.title, progress_callback)
        return report

    def _download_one(
        self,
        paper: PaperRecord,
        url: str,
        source: str,
        output_dir: Path,
        seen_hashes: dict[str, Path],
    ) -> DownloadItemResult:
        # Include bibliographic information when available, preserving the old
        # title-only format for incomplete source metadata.
        components = []
        if paper.publication_year:
            components.append(str(paper.publication_year))
        if paper.authors:
            components.append(paper.authors[0].split(",")[0].strip())
        components.append(paper.title)
        destination = output_dir / safe_filename("_".join(components))
        if destination.exists():
            suffix = destination.suffix
            stem = destination.stem
            tag = hashlib.sha256(url.encode("utf-8")).hexdigest()[:8]
            destination = output_dir / f"{stem}_{tag}{suffix}"
        last_error = "download failed"
        for attempt in range(1, self.max_attempts + 1):
            try:
                artifact = self.downloader.download(url, destination)
                if artifact.sha256 in seen_hashes:
                    if destination.exists() and destination != seen_hashes[artifact.sha256]:
                        destination.unlink()
                    local_path = seen_hashes[artifact.sha256]
                else:
                    seen_hashes[artifact.sha256] = artifact.path
                    local_path = artifact.path
                return DownloadItemResult(
                    paper=paper,
                    status=DownloadStatus.DOWNLOADED,
                    source_url=artifact.url,
                    source=source,
                    local_path=local_path,
                    sha256=artifact.sha256,
                    size_bytes=artifact.size_bytes,
                    attempts=attempt,
                )
            except DownloadFailure as exc:
                last_error = str(exc)
                if not exc.retryable or attempt == self.max_attempts:
                    return DownloadItemResult(
                        paper=paper,
                        status=(
                            DownloadStatus.INVALID_PDF
                            if exc.invalid_pdf
                            else DownloadStatus.ACCESS_RESTRICTED
                            if exc.access_restricted
                            else DownloadStatus.FAILED
                        ),
                        source_url=url,
                        source=source,
                        attempts=attempt,
                        error=last_error,
                    )
        return DownloadItemResult(
            paper=paper,
            status=DownloadStatus.FAILED,
            source_url=url,
            source=source,
            attempts=self.max_attempts,
            error=last_error,
        )

    def retry_failed(
        self,
        report: BatchDownloadReport,
        output_dir: Path,
        *,
        progress_callback: Callable[[DownloadProgress], None] | None = None,
    ) -> BatchDownloadReport:
        failed_papers = [
            item.paper
            for item in report.items
            if item.status
            in {
                DownloadStatus.FAILED,
                DownloadStatus.INVALID_PDF,
                DownloadStatus.ACCESS_RESTRICTED,
            }
        ]
        if not failed_papers:
            return report
        retried = self.download(
            failed_papers,
            output_dir,
            progress_callback=progress_callback,
        )
        # Keep successful items and original ordering; update only failed entries.
        replacements = iter(retried.items)
        new_items = [
            next(replacements) if item.status in {
                DownloadStatus.FAILED,
                DownloadStatus.INVALID_PDF,
                DownloadStatus.ACCESS_RESTRICTED,
            } else item
            for item in report.items
        ]
        return BatchDownloadReport(items=new_items)

    @staticmethod
    def _progress(
        report: BatchDownloadReport,
        completed: int,
        total: int,
        title: str,
        callback: Callable[[DownloadProgress], None] | None,
    ) -> None:
        if callback:
            callback(
                DownloadProgress(
                    completed=completed,
                    total=total,
                    current_title=title,
                    successes=report.success_count,
                    failures=report.failure_count,
                )
            )


def export_zip(report: BatchDownloadReport, zip_path: Path) -> Path:
    import zipfile

    zip_path.parent.mkdir(parents=True, exist_ok=True)
    used_names: set[str] = set()
    used_hashes: set[str] = set()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for item in report.downloaded:
            if not item.local_path or not item.local_path.exists():
                continue
            if item.sha256 and item.sha256 in used_hashes:
                continue
            name = item.local_path.name
            stem = item.local_path.stem
            suffix = item.local_path.suffix
            counter = 2
            while name in used_names:
                name = f"{stem}_{counter}{suffix}"
                counter += 1
            used_names.add(name)
            if item.sha256:
                used_hashes.add(item.sha256)
            archive.write(item.local_path, arcname=name)
    return zip_path
