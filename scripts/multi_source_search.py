from __future__ import annotations

import argparse
import json

from clients.crossref import CrossrefClient
from clients.openalex import OpenAlexClient
from clients.semantic_scholar import SemanticScholarClient
from core.cache import JsonFileCache
from core.settings import Settings
from repositories.database import create_database_engine
from repositories.search import SearchRepository
from services.search.retrieval import search_sources


def main() -> None:
    parser = argparse.ArgumentParser(description="Search scholarly APIs and save to SQLite.")
    parser.add_argument("query")
    parser.add_argument("--max-results", type=int, default=10)
    parser.add_argument("--from-year", type=int)
    parser.add_argument("--to-year", type=int)
    args = parser.parse_args()

    settings = Settings.from_env()
    cache = JsonFileCache(settings.cache_dir, settings.cache_ttl_seconds)
    clients = {
        "openalex": OpenAlexClient(
            email=settings.openalex_email,
            api_key=settings.openalex_api_key,
            timeout=settings.http_timeout_seconds,
            cache=cache,
        ),
        "semantic_scholar": SemanticScholarClient(
            api_key=settings.semantic_scholar_api_key,
            timeout=settings.http_timeout_seconds,
            cache=cache,
        ),
        "crossref": CrossrefClient(
            mailto=settings.crossref_mailto,
            timeout=settings.http_timeout_seconds,
            cache=cache,
        ),
    }
    report = search_sources(
        clients,
        args.query,
        max_results=args.max_results,
        from_year=args.from_year,
        to_year=args.to_year,
    )
    session_id = SearchRepository(create_database_engine(settings.database_url)).save_search(
        args.query,
        report.papers,
        parameters={
            "sources": list(clients),
            "from_year": args.from_year,
            "to_year": args.to_year,
            "max_results": args.max_results,
        },
    )
    print(
        json.dumps(
            {
                "session_id": session_id,
                "source_counts": report.source_counts,
                "source_errors": report.source_errors,
                "deduplicated_count": len(report.papers),
                "papers": [paper.model_dump(mode="json") for paper in report.papers],
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
