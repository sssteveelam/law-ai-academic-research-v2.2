# Engineering Notes

## Scope

This repository is being delivered milestone by milestone. M0–M4 code is present. V2 updates backend and lawful full-text downloader.
Advanced research features are not implemented. Offline backend tests have been
run, but the Streamlit UI and live external API interactions require additional
validation in a fully provisioned environment.

## Rules

- Keep source metadata provenance (`source_api`, `source_id`, and raw identifiers).
- Never infer a quartile when a trusted ranking row is absent.
- Preserve the quality rule as `quartile match OR whitelist match`.
- Do not treat an article landing page as a verified PDF.
- Do not add credentials, tokens, or personal data to source control or logs.
- Use network-free tests by default. Live API calls are opt-in smoke checks.
- Use UTF-8 for Vietnamese text and run commands from the repository root.

## Commands

```powershell
uv sync --extra dev
uv run pytest
uv run ruff check .
uv run streamlit run app/main.py
```

The OpenAlex smoke command is:

```powershell
uv run python scripts/openalex_search.py "artificial intelligence liability"
```

It requires Internet access and is not part of the deterministic test suite.

The M1 combined search command is:

```powershell
uv run python scripts/multi_source_search.py "fault causation explaining AI" --max-results 5
```

It calls OpenAlex, Semantic Scholar, and Crossref, isolates a source-level
failure such as HTTP 429, deduplicates the combined records, and persists the
search session to SQLite.

M2 quality engine tests:

```powershell
uv run pytest tests/test_scimago.py tests/test_whitelist.py tests/test_quality_engine.py tests/test_relevance.py
```

M3 full-text tests:

```powershell
uv run pytest tests/test_fulltext.py
```

Full-text code may use only explicit lawful OA/repository PDF candidates or
Unpaywall `url_for_pdf` values. It must not automate paywalls, CAPTCHA, login,
or publisher access controls.

M4 UI smoke:

```powershell
uv run streamlit run app/main.py
```

The six views are backed by SQLite and the real search/download services. Do
not add fixture papers to runtime code; fixtures belong in tests only.
