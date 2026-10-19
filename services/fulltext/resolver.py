from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse

from clients.openalex import OpenAlexClient
from clients.unpaywall import UnpaywallClient
from models.domain import DownloadStatus, PaperRecord


@dataclass(frozen=True)
class FullTextCandidate:
    url: str
    source: str
    direct_pdf: bool


@dataclass(frozen=True)
class FullTextResolution:
    status: DownloadStatus
    candidate: FullTextCandidate | None
    landing_page_url: str | None
    candidates: tuple[FullTextCandidate, ...]
    reason: str


class FullTextResolver:
    """Resolve only explicit lawful OA/repository links plus a fallback landing page."""

    def __init__(
        self,
        unpaywall: UnpaywallClient | None = None,
        openalex: OpenAlexClient | None = None,
    ) -> None:
        self.unpaywall = unpaywall
        self.openalex = openalex
        self._oa_by_doi: dict[str, PaperRecord] = {}
        self._lookup_error: str | None = None

    def prime(self, papers: list[PaperRecord]) -> None:
        """Bulk DOI refresh finds alternatives even when a stored PDF URL is stale."""
        self._oa_by_doi = {}
        self._lookup_error = None
        if self.openalex is None:
            return
        # Existing candidates may return 403/404. Refresh their alternative OA
        # locations too, so a failed link does not prevent repository fallback.
        dois = [p.doi for p in papers if p.doi]
        if not dois:
            return
        try:
            self._oa_by_doi = self.openalex.lookup_dois(dois)
        except Exception as exc:
            # An unavailable API must not block direct PDFs or Unpaywall.
            detail = str(exc).strip()[:120]
            self._lookup_error = (
                f"OpenAlex lookup unavailable ({type(exc).__name__}: {detail})"
            )

    def resolve(self, paper: PaperRecord) -> FullTextResolution:
        candidates: list[FullTextCandidate] = []
        if paper.pdf_url and _is_http_url(paper.pdf_url):
            candidates.append(
                FullTextCandidate(
                    url=paper.pdf_url,
                    source=_source_for_paper(paper),
                    direct_pdf=True,
                )
            )
        for url in paper.oa_locations:
            if url and _is_http_url(url) and url not in {candidate.url for candidate in candidates}:
                candidates.append(
                    FullTextCandidate(url=url, source="repository", direct_pdf=True)
                )
        if paper.doi and paper.doi in self._oa_by_doi:
            openalex_paper = self._oa_by_doi[paper.doi]
            for url in [openalex_paper.pdf_url, *openalex_paper.oa_locations]:
                if url and _is_http_url(url) and url not in {item.url for item in candidates}:
                    candidates.append(FullTextCandidate(url, "openalex", True))
        unpaywall_error: str | None = None
        if self.unpaywall and paper.doi:
            try:
                payload = self.unpaywall.lookup(paper.doi)
            except Exception as exc:
                # Do not silently misreport an unavailable API as no OA exists.
                payload = {}
                unpaywall_error = f"Unpaywall lookup unavailable ({type(exc).__name__})"
            for location in _unpaywall_locations(payload):
                if location.url not in {candidate.url for candidate in candidates}:
                    candidates.append(location)
        lookup_errors = "; ".join(
            error for error in (self._lookup_error, unpaywall_error) if error
        )
        if candidates:
            return FullTextResolution(
                status=DownloadStatus.OA_FOUND,
                candidate=candidates[0],
                landing_page_url=paper.landing_page_url,
                candidates=tuple(candidates),
                reason="lawful open-access candidate found",
            )
        if paper.landing_page_url:
            return FullTextResolution(
                status=DownloadStatus.ACCESS_RESTRICTED,
                candidate=None,
                landing_page_url=paper.landing_page_url,
                candidates=(),
                reason=(
                    "No lawful OA PDF was found; landing page retained. "
                    + lookup_errors
                ).strip(),
            )
        return FullTextResolution(
            status=DownloadStatus.NOT_CHECKED,
            candidate=None,
            landing_page_url=None,
            candidates=(),
            reason=("No lawful OA PDF found. " + lookup_errors).strip(),
        )


def _source_for_paper(paper: PaperRecord) -> str:
    for source in ("openalex", "semantic_scholar"):
        if source in paper.metadata_sources:
            return source
    return "metadata"


def _unpaywall_locations(payload: dict[str, Any]) -> list[FullTextCandidate]:
    locations = []
    best = payload.get("best_oa_location")
    if isinstance(best, dict):
        locations.append(best)
    locations.extend(
        item for item in payload.get("oa_locations", []) if isinstance(item, dict)
    )
    candidates: list[FullTextCandidate] = []
    for location in locations:
        url = location.get("url_for_pdf")
        if not isinstance(url, str) or not _is_http_url(url):
            continue
        candidates.append(
            FullTextCandidate(
                url=url,
                source="unpaywall",
                direct_pdf=True,
            )
        )
    return candidates


def _is_http_url(value: str) -> bool:
    return urlparse(value).scheme in {"http", "https"}
