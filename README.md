# Law & AI Academic Research Platform

An evidence-aware research workspace for legal scholarship on artificial
intelligence, liability, causation, fault, and related topics. The project is
being built incrementally, with source provenance and unverified evidence
kept explicit.

## Bản cập nhật V2.2 (Sửa cấu trúc OpenAlex PDF URL và fallback OA)

**Đọc [V2_2_OPENALEX_PDF_FIX.md](V2_2_OPENALEX_PDF_FIX.md)** trước khi triển khai. V2.2 sửa lỗi đọc trường `pdf_url` của OpenAlex và tìm lại nguồn OA cho bài có link PDF đã cũ hoặc lỗi. Cấu hình email Unpaywall/key OpenAlex rồi **khởi động lại Streamlit** để áp dụng.

## Bản cập nhật V2.1 (Fix tải PDF từ DOI-only legacy library)

**Xem [V2_1_PDF_FIX.md](V2_1_PDF_FIX.md)** để biết nguồn gốc lỗi, lệnh chẩn đoán một DOI, cách dùng nút tải về trình duyệt và các giới hạn mạng/Open Access.

## Bản cập nhật V2 (Backend + PDF)

Đã cập nhật kết nối SQLite → SCImago/whitelist khi tìm kiếm, khử trùng, xử lý SJR theo edition, downloader streaming có kiểm tra redirect/DNS và retry giữ kết quả thành công. Xem [V2_BACKEND_PDF_CHANGELOG.md](V2_BACKEND_PDF_CHANGELOG.md) để biết chi tiết và giới hạn kiểm thử.

**Lưu ý:** Lịch sử dữ liệu cũ trong `data/research.db` là bản sao của ZIP người dùng; nên tạo backup trước khi sử dụng trên máy chính. Không kèm file `.env` có API key; tự sao chép từ `.env.example`.

## Current status

**M4 complete:** project documentation, package layout, SQLite schema,
configurable research profile, cached/retrying OpenAlex/Semantic Scholar/
Crossref adapters, normalized multi-source records, conservative
deduplication, search-session persistence, SCImago import, ISSN/ISSN-L
matching, journal whitelist, Recommended/Broad/Custom filtering, and
deterministic relevance scoring, lawful full-text resolution, PDF validation,
retryable download queue, progress reporting, duplicate suppression, and ZIP
export, and the six-view Streamlit workspace are implemented.

Advanced research features such as author discovery and optional Zotero
integration are planned but are not yet complete.

Full-text resolution never bypasses paywalls, CAPTCHA, publisher login, or
other access controls. A publisher/DOI landing page is retained as a fallback
link when no direct lawful PDF is available.

## Windows runbook

From PowerShell:

```powershell
cd D:\law-ai-academic-research
uv sync --extra dev
Copy-Item .env.example .env
uv run pytest
uv run ruff check .
uv run streamlit run app/main.py
```

Open `http://localhost:8501`. Configure only environment values in `.env`;
never paste API keys into the repository or Streamlit source. The app creates
the SQLite database, cache, and download directories when needed.

## Windows setup

From `D:\law-ai-academic-research` in PowerShell:

```powershell
uv sync --extra dev
Copy-Item .env.example .env
uv run pytest
uv run ruff check .
uv run streamlit run app/main.py
```

The Streamlit app is local-only by default. OpenAlex permits a few demo
queries without a key, but a free OpenAlex API key is recommended for
routine use; `LAW_RESEARCH_OPENALEX_EMAIL` is contact metadata. Set
`LAW_RESEARCH_UNPAYWALL_EMAIL` to a valid email to enable Unpaywall.

## Multi-source search and SQLite persistence

```powershell
uv run python scripts/multi_source_search.py "fault causation explaining AI" --max-results 5
```

The command calls all three configured metadata sources, reports per-source
errors, deduplicates the combined records, and saves one `search_session` and
its `search_results` into SQLite.

For M2 ranking/filtering, import SJR CSV in Journal Management (persisted in SQLite), choose
Recommended, Broad, or Custom mode, and optionally enable the Q3/Q4 reference
list. Missing SJR data remains `Unknown`; it is never inferred from a journal
publisher or name.

## OpenAlex smoke test

```powershell
uv run python scripts/openalex_search.py "fault causation explaining AI" --per-page 5
```

This command performs a real network request and reports its result separately
from offline tests. A timeout or rate limit is an environment result, not proof
that the adapter is broken.

## Layout

See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md),
[docs/IMPLEMENTATION_PLAN.md](docs/IMPLEMENTATION_PLAN.md),
[docs/OPEN_QUESTIONS.md](docs/OPEN_QUESTIONS.md), and
[docs/DEPLOYMENT.md](docs/DEPLOYMENT.md).
