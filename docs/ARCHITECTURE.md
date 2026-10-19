# Architecture

The application is layered so Streamlit is an orchestration surface rather
than the home of business logic.

The M4 Streamlit shell routes six views through the same services and
repositories: dashboard, academic search, paper library, download manager,
journal management, and research settings. It does not maintain a separate
mock data layer.

```text
Streamlit app
    -> services/search (query plan + retrieval)
        -> clients/openalex, semantic_scholar, crossref
           (HTTP, retry, pagination, normalization)
        -> core/cache (filesystem TTL cache)
    -> services/search/normalization (deduplication + provenance merge)
    -> services/ranking (SCImago import, ISSN identity, whitelist, OR modes)
    -> services/relevance (deterministic explainable scoring)
    -> services/fulltext (OA resolver, PDF validation, queue, ZIP export)
    -> models (Pydantic domain contracts)
    -> repositories (SQLAlchemy search/ranking persistence)
```

`clients` own external API behavior. `services` own cross-source behavior and
later ranking/deduplication. `models` define stable contracts. `core` owns
configuration, errors, logging, and infrastructure concerns.

OpenAlex and Crossref use cursor pagination; Semantic Scholar uses offset
pagination. All adapters use bounded retries for timeout/429/5xx responses,
`Retry-After` when supplied, and deterministic cache keys derived from endpoint
and parameters. A failed external source is isolated and reported while other
sources continue. Cross-source records are deduplicated by DOI or external
identifier, with a conservative no-DOI title fallback.

M2 never infers a quartile from a publisher or journal name. SCImago rows are
matched by normalized ISSN/ISSN-L first; exact normalized journal names are a
fallback only when the paper has no ISSN. A known ISSN mismatch is not silently
overridden by a name match.

M3 treats PDF access as a separate boundary. Resolver candidates are explicit
OA/repository links or Unpaywall `url_for_pdf`; publisher landing pages are
fallback references, never download URLs. The downloader validates public
HTTP(S) URLs, redirects, response size, content type, and `%PDF-` signature.
