from __future__ import annotations

import argparse
import json

from clients.openalex import OpenAlexClient
from core.cache import JsonFileCache
from core.settings import Settings


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a live OpenAlex smoke search.")
    parser.add_argument("query")
    parser.add_argument("--per-page", type=int, default=5)
    parser.add_argument("--max-results", type=int, default=5)
    args = parser.parse_args()

    settings = Settings.from_env()
    client = OpenAlexClient(
        email=settings.openalex_email,
        api_key=settings.openalex_api_key,
        timeout=settings.http_timeout_seconds,
        cache=JsonFileCache(settings.cache_dir, settings.cache_ttl_seconds),
    )
    papers = client.search(args.query, per_page=args.per_page, max_results=args.max_results)
    payload = [paper.model_dump(mode="json") for paper in papers]
    print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
