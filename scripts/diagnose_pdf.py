"""Live Open Access diagnostic. Example: uv run python scripts/diagnose_pdf.py 10.xxxx/yyyy."""

from __future__ import annotations

import argparse
import sys

from clients.openalex import OpenAlexClient
from clients.unpaywall import UnpaywallClient
from core.cache import JsonFileCache
from core.settings import Settings
from models.domain import DownloadStatus, PaperRecord
from services.fulltext.downloader import PDFDownloader
from services.fulltext.queue import DownloadQueue
from services.fulltext.resolver import FullTextResolver


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Diagnose lawful PDF availability and write permissions for a DOI."
    )
    parser.add_argument("doi", help="e.g. 10.1371/journal.pone.0266781")
    args = parser.parse_args()
    doi = args.doi.strip().lower().removeprefix("https://doi.org/")
    if not doi.startswith("10.") or "/" not in doi:
        parser.error("Please provide a DOI such as 10.1371/journal.pone.0266781")

    config = Settings.from_env()
    cache = JsonFileCache(config.cache_dir, config.cache_ttl_seconds)
    print("Testing Open Access PDF discovery and download")
    print(f"DOI: {doi}")
    print(f"OpenAlex API key configured: {bool(config.openalex_api_key)}")
    print(f"Unpaywall contact email configured: {bool(config.unpaywall_email)}")
    print(f"System proxy enabled for PDF requests: {config.download_use_system_proxy}")
    print(f"Download destination: {config.download_dir.resolve()}")
    paper = PaperRecord(
        source_api="diagnostic",
        source_id=doi,
        doi=doi,
        title=f"OA diagnostic {doi}",
        landing_page_url=f"https://doi.org/{doi}",
    )
    openalex = OpenAlexClient(
        email=config.openalex_email,
        api_key=config.openalex_api_key,
        timeout=config.http_timeout_seconds,
        max_retries=1,
        cache=cache,
    )
    unpaywall = (
        UnpaywallClient(
            email=config.unpaywall_email,
            timeout=config.http_timeout_seconds,
            max_retries=1,
            cache=cache,
        )
        if config.unpaywall_email else None
    )
    queue = DownloadQueue(
        FullTextResolver(unpaywall, openalex=openalex),
        PDFDownloader(
            max_bytes=config.max_download_bytes,
            trust_env=config.download_use_system_proxy,
        ),
        max_attempts=2,
    )
    report = queue.download([paper], config.download_dir)
    item = report.items[0]
    print(f"Result: {item.status.value}")
    print(f"Metadata source: {item.source or 'n/a'}")
    print(f"Error / explanation: {item.error or '(none)'}")
    if item.status == DownloadStatus.DOWNLOADED and item.local_path:
        print(f"Saved PDF: {item.local_path.resolve()}")
        print(f"Size (bytes): {item.size_bytes}")
        return 0
    if item.status == DownloadStatus.ACCESS_RESTRICTED:
        print("This DOI may have no lawful, downloadable OA PDF. Try a known OA DOI.")
        return 1
    return 2


if __name__ == "__main__":
    sys.exit(main())
