# Implementation Plan

## M0 — foundation (implemented)

- Requirements, architecture, schema, test plan, and open questions.
- Python packaging, environment example, lint/test configuration.
- SQLAlchemy model foundation.
- Configurable initial research profile.

## M1 — search engine (implemented)

- OpenAlex adapter and offline contract tests (implemented).
- Persist normalized results and deduplicate across sources.
- Add Semantic Scholar and Crossref adapters with the same contract.
- Add multi-source query planner and partial-failure reporting.
- Live API smoke checks remain opt-in and are reported separately from tests.

## M2 — quality engine (implemented)

- Import SCImago CSV with explicit year/subject joins.
- Journal identity matching by ISSN/ISSN-L before conservative name variants.
- Implement quartile-or-whitelist acceptance and explainable relevance scoring.
- Add Recommended/Broad/Custom mode decisions and keep reference results
  separate from priority results.
- Persist imported ranking and editable whitelist entries in SQLite.

## M3 — full text (implemented)

- Lawful OA resolver, URL safety checks, PDF signature validation, retries,
  per-item failure isolation, ZIP export.
- Download progress callbacks, duplicate suppression, retry-failed operation,
  and additive SQLite download-task fields.

## M4 — Streamlit UI (implemented)

- Research Dashboard, Academic Search, Paper Library, Download Manager,
  Journal Management, and Research Settings.
- Stable paper-ID selection, CSV/Excel export, real download queue wiring,
  and Windows runbook.

## M5–M6

- Author discovery, optional Zotero integration, integration/E2E coverage,
  performance review, and delivery hardening.
