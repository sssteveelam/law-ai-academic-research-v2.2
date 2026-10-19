# Requirements

## Confirmed

- Streamlit application for a law PhD researcher.
- Search must support changing topics without source edits.
- Primary metadata sources are OpenAlex, Semantic Scholar, and Crossref.
- Open-access metadata and lawful repository links are separate from publisher
  landing pages.
- Quality acceptance is an OR rule: selected quartile **or** target-journal
  whitelist.
- Quartiles must come from imported, year/subject-aware ranking data; no
  publisher-name inference is allowed.
- Search results retain rejected candidates for inspection where practical.
- All external metadata retains source API and source identifier.
- SQLite and SQLAlchemy are the MVP persistence layer.
- Network-free pytest tests are required.
- Credentials must be environment-based and never committed.

## Current M0/M1 slice

- Configurable keyword and journal profile files.
- Validated normalized paper contract.
- SQLite model foundation for future repositories.
- OpenAlex query planning, pagination, retry/backoff, cache, and normalization.
- Streamlit shell that can run an OpenAlex search and display results.

## M2 quality engine

- SCImago SJR CSV import with explicit year/subject context.
- ISSN/ISSN-L-first journal matching and conservative name fallback.
- Editable whitelist matching without substring false positives.
- Recommended, Broad, and Custom quality modes using quartile OR whitelist.
- Deterministic relevance scoring kept separate from journal quality.

## M3 full-text engine

- Resolve explicit lawful OA candidates from OpenAlex/Semantic Scholar
  metadata, repositories, and Unpaywall.
- Preserve publisher/DOI landing pages as fallback links only.
- Validate HTTP status, redirects, public URL safety, content type, PDF
  signature, and maximum size.
- Process a selected batch with per-item retry, progress callbacks, failure
  isolation, safe filenames, duplicate suppression, and ZIP export.

## M4 Streamlit UI

- Research Dashboard with live SQLite metrics and recent searches.
- Academic Search connected to the real scholarly adapters and M2 quality
  controls.
- Paper Library with filtering, sorting, stable SQLite paper-ID selection,
  CSV/Excel export, and selected-paper download actions.
- Download Manager with per-item status/error, retry failed, progress, and ZIP.
- Journal Management with SJR/whitelist CSV import and persisted identity data.
- Research Settings with environment status, keyword presets, and search
  history.
