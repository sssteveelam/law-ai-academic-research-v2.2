# Windows Setup

Run these commands in PowerShell from `D:\law-ai-academic-research`:

```powershell
uv sync --extra dev
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
uv run pytest
uv run ruff check .
uv run streamlit run app/main.py
```

Open `http://localhost:8501`.

The six workspace views are selected from the sidebar:

- Research Dashboard
- Academic Search
- Paper Library
- Download Manager
- Journal Management
- Research Settings

Academic Search calls OpenAlex, Semantic Scholar, and Crossref according to
the selected sources. Journal Management accepts SJR and whitelist CSV files.
Paper Library selection is keyed by the SQLite `papers.id`, not by table row
position. Download Manager receives the real queue report and exposes retry
errors and a ZIP of successful PDFs.

The app automatically loads `.env` from the repository root. Optional values:

```text
LAW_RESEARCH_OPENALEX_EMAIL=researcher@example.org
LAW_RESEARCH_CROSSREF_MAILTO=researcher@example.org
LAW_RESEARCH_UNPAYWALL_EMAIL=researcher@example.org
LAW_RESEARCH_SEMANTIC_SCHOLAR_API_KEY=
LAW_RESEARCH_DOWNLOAD_DIR=data/downloads
```

Semantic Scholar requests are automatically spaced at about 1.1 seconds to
stay below the approved 1 request/second limit.

Do not commit `.env`, API keys, institutional tokens, or downloaded PDFs.

Unpaywall needs a real contact email. Without it, papers that only have a DOI
or publisher landing page are reported as `ACCESS_RESTRICTED` and are not
downloaded.
