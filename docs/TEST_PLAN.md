# Test Plan

## Deterministic tests

- Query planning and URL/parameter construction.
- OpenAlex normalization, inverted-index abstracts, missing metadata.
- Semantic Scholar normalization, offset pagination, and OA PDF metadata.
- Crossref normalization, cursor pagination, and publisher landing-page
  provenance without claiming a verified PDF.
- Retry behavior for timeout, 429, and 5xx.
- Cursor/offset pagination and cache reuse.
- DOI/identifier deduplication, conservative no-DOI fallback, and
  cross-source provenance merging.
- Partial-failure reporting when one source is unavailable.
- Search-session persistence, paper upsert, and author relationships.
- PDF signature/content-type validation, redirect and SSRF URL checks.
- 403/404 and transient retry handling.
- Per-item batch failure isolation, progress callbacks, duplicate suppression,
  retry-failed, and ZIP membership.

## Integration tests

Use a local HTTP test server or injected transport. Do not require Internet,
API keys, or a live SCImago file.

## Live smoke checks

`scripts/openalex_search.py` is an opt-in OpenAlex check.
`scripts/multi_source_search.py` is an opt-in combined OpenAlex/Semantic
Scholar/Crossref check that also writes SQLite. Record the date, query,
response counts, deduplicated count, and any rate-limit/timeout result; never
treat live checks as a replacement for deterministic tests.

M3 tests use injected `httpx.MockTransport` responses. Their success rate is a
deterministic fixture metric, not a claim about live publisher or repository
availability.
