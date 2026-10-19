from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
load_dotenv(PROJECT_ROOT / ".env")


def _config_value(name: str, default: str | None = None) -> str | None:
    value = os.getenv(name)
    if value is not None and value.strip():
        return value
    try:
        import streamlit as st

        secret_value = st.secrets.get(name)
    except Exception:
        secret_value = None
    if secret_value is None:
        return default
    return str(secret_value)


def _int_env(name: str, default: int) -> int:
    value = _config_value(name)
    if value is None or value.strip() == "":
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer") from exc


@dataclass(frozen=True)
class Settings:
    database_url: str
    cache_dir: Path
    cache_ttl_seconds: int
    openalex_email: str | None
    openalex_api_key: str | None
    semantic_scholar_api_key: str | None
    crossref_mailto: str | None
    unpaywall_email: str | None
    http_timeout_seconds: float
    max_download_bytes: int
    download_dir: Path
    download_use_system_proxy: bool = False

    @classmethod
    def from_env(cls) -> Settings:
        timeout_raw = _config_value("LAW_RESEARCH_HTTP_TIMEOUT_SECONDS", "20") or "20"
        try:
            timeout = float(timeout_raw)
        except ValueError as exc:
            raise ValueError("LAW_RESEARCH_HTTP_TIMEOUT_SECONDS must be numeric") from exc
        return cls(
            database_url=(
                _config_value("LAW_RESEARCH_DATABASE_URL", "sqlite:///data/research.db")
                or "sqlite:///data/research.db"
            ),
            cache_dir=Path(_config_value("LAW_RESEARCH_CACHE_DIR", "data/cache") or "data/cache"),
            cache_ttl_seconds=_int_env("LAW_RESEARCH_CACHE_TTL_SECONDS", 86400),
            openalex_email=_config_value("LAW_RESEARCH_OPENALEX_EMAIL"),
            openalex_api_key=_config_value("LAW_RESEARCH_OPENALEX_API_KEY"),
            semantic_scholar_api_key=_config_value("LAW_RESEARCH_SEMANTIC_SCHOLAR_API_KEY"),
            crossref_mailto=_config_value("LAW_RESEARCH_CROSSREF_MAILTO"),
            unpaywall_email=_config_value("LAW_RESEARCH_UNPAYWALL_EMAIL"),
            http_timeout_seconds=timeout,
            max_download_bytes=_int_env("LAW_RESEARCH_MAX_DOWNLOAD_BYTES", 50 * 1024 * 1024),
            download_dir=Path(
                _config_value("LAW_RESEARCH_DOWNLOAD_DIR", "data/downloads")
                or "data/downloads"
            ),
            download_use_system_proxy=(
                (_config_value("LAW_RESEARCH_DOWNLOAD_USE_SYSTEM_PROXY", "false") or "")
                .lower() in {"1", "true", "yes"}
            ),
        )
