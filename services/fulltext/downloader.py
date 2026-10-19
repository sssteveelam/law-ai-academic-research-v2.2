from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urljoin

import httpx

from services.fulltext.security import (
    UnsafeURL,
    validate_public_dns_host,
    validate_public_http_url,
)


class DownloadFailure(Exception):
    def __init__(
        self,
        message: str,
        *,
        retryable: bool = False,
        invalid_pdf: bool = False,
        access_restricted: bool = False,
    ):
        super().__init__(message)
        self.retryable = retryable
        self.invalid_pdf = invalid_pdf
        self.access_restricted = access_restricted


@dataclass(frozen=True)
class DownloadedArtifact:
    path: Path
    url: str
    sha256: str
    size_bytes: int
    content_type: str


class PDFDownloader:
    """Stream lawful PDF candidates, checking each redirect before connecting."""

    def __init__(
        self,
        *,
        client: httpx.Client | None = None,
        max_bytes: int = 50 * 1024 * 1024,
        max_redirects: int = 5,
        dns_check: Callable[[str], None] | None = None,
        trust_env: bool = False,
    ) -> None:
        # Proxy use is opt-in. Direct HTTP requests are safest for SSRF control.
        self.client = client or httpx.Client(
            follow_redirects=False, trust_env=trust_env, timeout=30,
            headers={"Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.5",
                     "User-Agent": "LawAIResearch/2.1 (lawful open-access PDF retrieval)"},
        )
        self.max_bytes = max_bytes
        self.max_redirects = max_redirects
        # MockTransport has no external network or DNS to resolve.
        self.dns_check = dns_check if dns_check is not None else (
            (lambda _url: None)
            if isinstance(getattr(self.client, "_transport", None), httpx.MockTransport)
            else validate_public_dns_host
        )

    def download(
        self,
        url: str,
        destination: Path,
        *,
        progress: Callable[[int, int | None], None] | None = None,
    ) -> DownloadedArtifact:
        temp_path = destination.with_suffix(destination.suffix + ".part")
        current_url = url
        try:
            for redirect_count in range(self.max_redirects + 1):
                validate_public_http_url(current_url)
                self.dns_check(current_url)
                # Explicitly disable redirects even when the supplied client has them enabled.
                with self.client.stream("GET", current_url, follow_redirects=False) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise DownloadFailure("redirect missing Location header")
                        if redirect_count == self.max_redirects:
                            raise DownloadFailure("too many redirects")
                        current_url = urljoin(current_url, location)
                        continue
                    if response.status_code in {401, 403}:
                        raise DownloadFailure(
                            f"HTTP {response.status_code}: access denied or OA link unavailable",
                            access_restricted=True,
                        )
                    if response.status_code in {404, 410}:
                        raise DownloadFailure(f"HTTP {response.status_code}: PDF not found")
                    if response.status_code in {408, 429} or response.status_code >= 500:
                        raise DownloadFailure(f"HTTP {response.status_code}", retryable=True)
                    if response.status_code != 200:
                        raise DownloadFailure(f"HTTP {response.status_code}")
                    content_type = response.headers.get("content-type", "").split(";", 1)[0].strip().lower()
                    # Repositories sometimes return PDFs as text/plain or a generic
                    # binary MIME type. Verify the actual PDF signature, not MIME alone.
                    # An HTML/login response will fail the signature check below.
                    declared_size = _parse_content_length(response.headers.get("content-length"))
                    if declared_size is not None and declared_size > self.max_bytes:
                        raise DownloadFailure("content exceeds configured size limit", invalid_pdf=True)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    digest = hashlib.sha256()
                    total = 0
                    signature = b""
                    with temp_path.open("wb") as stream:
                        for chunk in response.iter_bytes(chunk_size=64 * 1024):
                            if not chunk:
                                continue
                            total += len(chunk)
                            if total > self.max_bytes:
                                raise DownloadFailure("content exceeds configured size limit", invalid_pdf=True)
                            if len(signature) < 5:
                                signature += chunk[:5 - len(signature)]
                                if len(signature) == 5 and signature != b"%PDF-":
                                    raise DownloadFailure("response is not a PDF", invalid_pdf=True)
                            stream.write(chunk)
                            digest.update(chunk)
                            if progress:
                                progress(total, declared_size)
                    if signature != b"%PDF-":
                        raise DownloadFailure("response is not a PDF", invalid_pdf=True)
                    temp_path.replace(destination)
                    return DownloadedArtifact(
                        path=destination,
                        url=str(response.url),
                        sha256=digest.hexdigest(),
                        size_bytes=total,
                        content_type=content_type or "application/pdf",
                    )
            raise DownloadFailure("too many redirects")
        except UnsafeURL as exc:
            raise DownloadFailure(str(exc), retryable=False) from exc
        except httpx.RequestError as exc:
            raise DownloadFailure(
                f"network error ({type(exc).__name__}); verify connectivity/proxy",
                retryable=True,
            ) from exc
        except OSError as exc:
            raise DownloadFailure(
                f"unable to save PDF ({type(exc).__name__}); check download folder permissions"
            ) from exc
        finally:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass


def safe_filename(title: str, suffix: str = ".pdf") -> str:
    normalized = unicodedata.normalize("NFKD", title)
    cleaned = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", cleaned).strip("._")
    cleaned = cleaned[:120].rstrip("._") or "paper"
    # Windows blocks reserved device filenames even with an extension.
    if cleaned.split(".", 1)[0].upper() in {
        "CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }:
        cleaned = "paper_" + cleaned
    if not cleaned.lower().endswith(suffix):
        cleaned += suffix
    return cleaned


def _parse_content_length(value: str | None) -> int | None:
    if not value or not value.isdigit():
        return None
    return int(value)
