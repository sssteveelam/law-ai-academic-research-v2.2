from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pandas as pd
import streamlit as st

from clients.crossref import CrossrefClient
from clients.openalex import OpenAlexClient
from clients.semantic_scholar import SemanticScholarClient
from clients.unpaywall import UnpaywallClient
from core.cache import JsonFileCache
from core.settings import Settings
from models.domain import DownloadStatus, Quartile
from repositories.database import create_database_engine
from repositories.downloads import DownloadRepository
from repositories.library import LibraryPaper, LibraryRepository
from repositories.ranking import RankingRepository
from repositories.search import SearchRepository
from repositories.settings import SettingsRepository
from services.fulltext.downloader import PDFDownloader
from services.fulltext.queue import BatchDownloadReport, DownloadQueue, export_zip
from services.fulltext.resolver import FullTextResolver
from services.ranking.engine import (
    ResearchFilterConfig,
    ResearchMode,
    filter_papers,
)
from services.ranking.identifiers import normalize_issn, split_issns
from services.ranking.scimago import ScimagoCSVImporter
from services.ranking.whitelist import JournalWhitelist, JournalWhitelistEntry
from services.relevance.scorer import KeywordProfile, apply_relevance
from services.search.planner import ResearchProfile
from services.search.retrieval import filter_papers_by_journals, search_sources

ROOT = Path(__file__).resolve().parents[1]
PAGES = [
    "Research Dashboard",
    "Academic Search",
    "Paper Library",
    "Download Manager",
    "Journal Management",
    "Research Settings",
]


def main() -> None:
    settings = Settings.from_env()
    engine = create_database_engine(settings.database_url)
    profile = ResearchProfile.from_file(ROOT / "config" / "research_profile.json")
    _initialize_state()
    _apply_pending_navigation()
    st.set_page_config(page_title="Law & AI Academic Research", layout="wide")
    st.title("Law & AI Academic Research")
    page = st.sidebar.radio("Workspace", PAGES, key="active_page")
    st.sidebar.caption(f"Database: {settings.database_url}")
    st.sidebar.markdown(
        "**Bắt đầu nhanh**  \n"
        "1. Mở **Academic Search** và bấm **Chạy tìm kiếm**.  \n"
        "2. Sang **Paper Library** để chọn bài.  \n"
        "3. Bấm **Download selected PDFs**.  \n"
        "4. Xem tiến độ và ZIP trong **Download Manager**."
    )

    if page == "Research Dashboard":
        render_dashboard(engine)
    elif page == "Academic Search":
        render_academic_search(settings, engine, profile)
    elif page == "Paper Library":
        render_library(settings, engine)
    elif page == "Download Manager":
        render_download_manager(settings, engine)
    elif page == "Journal Management":
        render_journal_management(engine)
    else:
        render_settings(settings, engine, profile)


def _initialize_state() -> None:
    defaults = {
        "selected_paper_ids": set(),
        "download_report": None,
        "last_search_id": None,
        "source_errors": {},
        "search_counts": {},
        "pending_page": None,
    }
    for key, value in defaults.items():
        st.session_state.setdefault(key, value)


def _apply_pending_navigation() -> None:
    pending_page = st.session_state.pop("pending_page", None)
    if pending_page in PAGES:
        st.session_state["active_page"] = pending_page


def _navigate(page: str) -> None:
    st.session_state["pending_page"] = page
    st.rerun()


def render_dashboard(engine: Any) -> None:
    st.header("Research Dashboard")
    st.caption("Live counts from the configured SQLite database.")
    metrics = LibraryRepository(engine).metrics()
    columns = st.columns(5)
    columns[0].metric("Papers", metrics["papers"])
    columns[1].metric("Q1 / Q2", f'{metrics["q1"]} / {metrics["q2"]}')
    columns[2].metric("Q3 / Q4", f'{metrics["q3"]} / {metrics["q4"]}')
    columns[3].metric("Whitelist", metrics["whitelist"])
    columns[4].metric("Downloaded PDFs", metrics["downloaded"])
    st.metric("Open-access candidates", metrics["oa"])

    st.subheader("Recent searches")
    sessions = LibraryRepository(engine).recent_sessions()
    if not sessions:
        st.info("Chưa có dữ liệu. Bắt đầu ở mục Academic Search.")
        if st.button("Mở Academic Search", type="primary"):
            _navigate("Academic Search")
        return
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Session": item["id"],
                    "Query": item["query"],
                    "Created": item["created_at"],
                    "Sources": ", ".join(item["parameters"].get("sources", [])),
                }
                for item in sessions
            ]
        ),
        width="stretch",
        hide_index=True,
    )


def render_academic_search(
    settings: Settings,
    engine: Any,
    profile: ResearchProfile,
) -> None:
    st.header("Academic Search")
    st.info(
        "1. Nhập chủ đề. 2. Chọn nguồn. 3. Bấm Chạy tìm kiếm. "
        "Sau đó mở Paper Library để chọn bài và tải PDF."
    )
    topic = st.text_input("Chủ đề hoặc truy vấn", value=profile.build_query())
    source_columns = st.columns([0.72, 0.28])
    sources = source_columns[0].multiselect(
        "Nguồn học thuật",
        ["OpenAlex", "Semantic Scholar", "Crossref"],
        default=["OpenAlex", "Semantic Scholar", "Crossref"],
    )
    max_results = source_columns[1].number_input(
        "Số bài mỗi nguồn",
        min_value=1,
        max_value=200,
        value=20,
    )
    ranking_repository = RankingRepository(engine)
    # Bootstrap default journals just once for a fresh database. Do not overwrite
    # subsequent user edits, removals, disabled entries, or CSV imports.
    _ensure_default_whitelist(ranking_repository, profile)
    target_journal_names = [
        item.name for item in ranking_repository.list_whitelist() if item.enabled
    ]
    journal_filter_enabled = st.checkbox(
        "Chỉ tìm trong tạp chí mục tiêu",
        value=False,
    )
    selected_target_journals = st.multiselect(
        "Tạp chí mục tiêu",
        target_journal_names,
        disabled=not journal_filter_enabled,
        placeholder="Chọn một hoặc nhiều tạp chí",
    )
    search_clicked = st.button("Chạy tìm kiếm", type="primary")
    with st.expander("Tùy chọn từ khóa và chất lượng", expanded=False):
        keyword_columns = st.columns(3)
        primary = keyword_columns[0].text_area(
            "Primary keywords",
            value="\n".join(profile.primary_keywords),
        )
        extended = keyword_columns[1].text_area(
            "Extended keywords",
            value="\n".join(profile.extended_keywords),
        )
        excluded = keyword_columns[2].text_area(
            "Excluded keywords",
            value="\n".join(profile.excluded_keywords),
        )
        year_columns = st.columns(2)
        from_year = year_columns[0].number_input(
            "From year", min_value=1900, max_value=2100, value=2000
        )
        to_year = year_columns[1].number_input(
            "To year", min_value=1900, max_value=2100, value=2100
        )
        mode = st.selectbox(
            "Quality mode",
            list(ResearchMode),
            format_func=lambda value: value.value,
        )
        selected_quartiles = st.multiselect(
            "Custom quartiles",
            ["Q1", "Q2", "Q3", "Q4"],
            default=["Q1", "Q2"],
            disabled=mode is not ResearchMode.CUSTOM,
        )
        include_reference = st.checkbox(
            "Include Q3/Q4 reference results",
            value=False,
            disabled=mode is not ResearchMode.RECOMMENDED,
        )
        ranking_year = st.number_input(
            "SJR ranking year (0 = use CSV/paper year)",
            min_value=0,
            max_value=2100,
            value=0,
        )
        ranking_subject = st.text_input("SJR subject/category (optional)")
        sjr_file = st.file_uploader("SJR CSV (optional)", type=["csv"])

    if not search_clicked:
        _render_source_errors()
        return
    if not topic.strip():
        st.error("Enter a research topic or query.")
        return
    if not sources:
        st.error("Select at least one scholarly source.")
        return
    if journal_filter_enabled and not selected_target_journals:
        st.error("Chọn ít nhất một tạp chí mục tiêu hoặc tắt bộ lọc tạp chí.")
        return
    try:
        if sjr_file is not None:
            uploaded_ranking = _load_sjr(sjr_file, int(ranking_year) or None, ranking_subject)
            if uploaded_ranking.rows:
                ranking_repository.replace_source_rows(uploaded_ranking.rows)
        ranking = ranking_repository.load_rankings()
    except ValueError as exc:
        st.error(f"SJR CSV error: {exc}")
        return
    keyword_profile = KeywordProfile(
        primary=_lines(primary),
        extended=_lines(extended),
        excluded=_lines(excluded),
    )
    clients = _build_clients(settings, sources)
    with st.spinner("Searching selected sources..."):
        report = search_sources(
            clients,
            topic,
            max_results=int(max_results),
            from_year=int(from_year),
            to_year=int(to_year),
        )
    candidate_papers = filter_papers_by_journals(
        report.papers,
        selected_target_journals if journal_filter_enabled else (),
    )
    whitelist = ranking_repository.load_whitelist()
    scored = apply_relevance(candidate_papers, keyword_profile)
    quality = filter_papers(
        scored,
        ranking,
        whitelist,
        ResearchFilterConfig(
            mode=mode,
            selected_quartiles=frozenset(Quartile(value) for value in selected_quartiles),
            include_reference=include_reference,
            ranking_year=int(ranking_year) or None,
            subject=ranking_subject or None,
        ),
    )
    all_papers = [*quality.priority, *quality.reference, *quality.excluded]
    session_id = SearchRepository(engine).save_search(
        topic,
        all_papers,
        parameters={
            "sources": list(clients),
            "from_year": int(from_year),
            "to_year": int(to_year),
            "max_results": int(max_results),
            "mode": mode.value,
            "selected_quartiles": selected_quartiles,
            "include_reference": include_reference,
            "ranking_year": int(ranking_year) or None,
            "ranking_subject": ranking_subject or None,
            "journal_filter_enabled": journal_filter_enabled,
            "target_journals": selected_target_journals,
        },
    )
    st.session_state["last_search_id"] = session_id
    st.session_state["source_errors"] = report.source_errors
    st.session_state["search_counts"] = report.source_counts
    st.session_state["selected_paper_ids"] = set()
    for key in list(st.session_state):
        if key.startswith("paper_selected_"):
            del st.session_state[key]
    st.success(f"Đã lưu phiên tìm kiếm #{session_id}.")
    result_columns = st.columns(4)
    result_columns[0].metric("Kết quả sau lọc", len(candidate_papers))
    result_columns[1].metric("Ưu tiên", len(quality.priority))
    result_columns[2].metric("Tham khảo", len(quality.reference))
    result_columns[3].metric("Loại khỏi ưu tiên", len(quality.excluded))
    if not ranking.rows:
        st.warning(
            "Chưa có dữ liệu SJR đã nhập nên quartile có thể là Unknown. "
            "Bài vẫn được lưu trong Paper Library để kiểm tra."
        )
    if candidate_papers:
        preview = pd.DataFrame(
            [
                {
                    "Paper ID": row.paper_id,
                    "Title": row.paper.title,
                    "Journal": row.paper.journal_name or "",
                    "Q": row.paper.quartile.value,
                    "Rule": row.paper.matched_rule or "NONE",
                    "Relevance": row.paper.relevance_score,
                }
                for row in LibraryRepository(engine).get_session_papers(session_id)[:10]
            ]
        )
        st.dataframe(preview, width="stretch", hide_index=True)
    if st.button("Mở Paper Library", type="primary"):
        _navigate("Paper Library")
    st.write("Số kết quả theo nguồn:", report.source_counts)
    _render_source_errors()


def render_library(settings: Settings, engine: Any) -> None:
    st.header("Paper Library")
    repository = LibraryRepository(engine)
    controls = st.columns(4)
    query = controls[0].text_input("Filter text")
    bucket = controls[1].selectbox(
        "Quality bucket", ["All", "priority", "reference", "excluded"]
    )
    quartile = controls[2].selectbox(
        "Quartile", ["All", "Q1", "Q2", "Q3", "Q4", "Unranked", "Unknown"]
    )
    sort_by = controls[3].selectbox(
        "Sort", ["relevance", "year", "title"], format_func=str.title
    )
    open_access_only = st.checkbox("Only papers with OA PDF candidates")
    rows = repository.list_papers(
        query=query,
        quality_bucket=None if bucket == "All" else bucket,
        quartile=None if quartile == "All" else quartile,
        open_access_only=open_access_only,
        sort_by=sort_by,
    )
    if not rows:
        st.info("No papers match the current filters.")
        return
    current_ids = {row.paper_id for row in rows}
    selected_ids: set[int] = st.session_state["selected_paper_ids"]
    actions = st.columns(3)
    if actions[0].button("Select all visible"):
        selected_ids.update(current_ids)
        for paper_id in current_ids:
            st.session_state[f"paper_selected_{paper_id}"] = True
        st.rerun()
    if actions[1].button("Clear selection"):
        selected_ids.difference_update(current_ids)
        for paper_id in current_ids:
            st.session_state[f"paper_selected_{paper_id}"] = False
        st.rerun()
    st.caption(f"{len(rows)} visible · {len(selected_ids)} selected")
    for row in rows:
        _render_library_row(row, selected_ids)
    selected_rows = [row for row in rows if row.paper_id in selected_ids]
    st.divider()
    export_columns = st.columns(3)
    csv_bytes, xlsx_bytes = _export_bytes(selected_rows or rows)
    export_columns[0].download_button(
        "Export CSV",
        data=csv_bytes,
        file_name="paper-library.csv",
        mime="text/csv",
        disabled=not selected_rows and not rows,
    )
    export_columns[1].download_button(
        "Export Excel",
        data=xlsx_bytes,
        file_name="paper-library.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        disabled=not selected_rows and not rows,
    )
    st.caption(
        "Only direct lawful PDF links are downloaded. DOI or publisher pages are "
        "kept as links and are never treated as PDF files."
    )
    if export_columns[2].button("Download selected PDFs", disabled=not selected_rows):
        _download_rows(settings, engine, selected_rows)


def render_download_manager(settings: Settings, engine: Any) -> None:
    st.header("Download Manager")
    report: BatchDownloadReport | None = st.session_state.get("download_report")
    if report is None:
        st.info("Chưa có đợt tải mới. Bạn có thể tải lại các PDF đã lưu trước đây.")
        _render_saved_pdf_history(engine, settings)
        return
    st.metric(
        "Success rate",
        f"{report.success_rate:.1%}",
        delta=f"{report.success_count}/{len(report.items)}",
    )
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Title": item.paper.title,
                    "Status": item.status.value,
                    "Source": item.source or "",
                    "Attempts": item.attempts,
                    "Bytes": item.size_bytes or 0,
                    "Error": item.error or "",
                }
                for item in report.items
            ]
        ),
        width="stretch",
        hide_index=True,
    )
    retryable = any(
        item.status
        in {
            DownloadStatus.FAILED,
            DownloadStatus.INVALID_PDF,
            DownloadStatus.ACCESS_RESTRICTED,
        }
        for item in report.items
    )
    if st.button("Retry failed", disabled=not retryable):
        queue = _build_download_queue(settings)
        with st.spinner("Retrying failed downloads..."):
            updated = queue.retry_failed(report, settings.download_dir)
            _persist_retry_results(engine, report, updated)
            st.session_state["download_report"] = updated
        st.rerun()
    _render_pdf_export_buttons(report, settings.download_dir)
    _render_download_results(report)
    with st.expander("PDF đã tải trong những phiên trước"):
        _render_saved_pdf_history(engine, settings)


def render_journal_management(engine: Any) -> None:
    st.header("Journal Management")
    repository = RankingRepository(engine)
    # Initialize default whitelist only when the DB is newly created.
    profile = ResearchProfile.from_file(ROOT / "config" / "research_profile.json")
    _ensure_default_whitelist(repository, profile)
    st.metric("Imported SJR rows", repository.ranking_count())
    with st.form("journal_import_form"):
        sjr_file = st.file_uploader("Import SCImago SJR CSV", type=["csv"])
        whitelist_file = st.file_uploader("Import whitelist CSV", type=["csv"])
        import_clicked = st.form_submit_button("Import selected files")
    if import_clicked:
        if not sjr_file and not whitelist_file:
            st.warning("Choose at least one CSV file.")
        else:
            try:
                if sjr_file:
                    ranking = ScimagoCSVImporter.from_text(
                        sjr_file.getvalue().decode("utf-8-sig")
                    )
                    count = repository.replace_source_rows(ranking.rows)
                    st.success(f"Imported {count} SJR journal rows.")
                if whitelist_file:
                    whitelist = JournalWhitelist.from_csv_text(
                        whitelist_file.getvalue().decode("utf-8-sig")
                    )
                    count = repository.upsert_whitelist(whitelist.entries)
                    st.success(f"Imported {count} whitelist journals.")
            except (UnicodeDecodeError, ValueError) as exc:
                st.error(f"Import failed: {exc}")
    entries = repository.list_whitelist()
    if entries:
        st.subheader("Current whitelist")
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Name": entry.name,
                        "Group": entry.group_name or "",
                        "ISSN": ", ".join(entry.issns or []),
                        "ISSN-L": entry.issn_l or "",
                        "Enabled": entry.enabled,
                        "Source": entry.source or "",
                    }
                    for entry in entries
                ]
            ),
            width="stretch",
            hide_index=True,
        )
    else:
        st.info("No whitelist has been imported yet.")
    st.subheader("Edit whitelist")
    with st.form("add_journal_form"):
        add_columns = st.columns(3)
        add_name = add_columns[0].text_input("Journal name")
        add_group = add_columns[1].text_input("Group")
        add_issn = add_columns[2].text_input("ISSN / ISSN-L")
        add_clicked = st.form_submit_button("Add journal")
    if add_clicked:
        if not add_name.strip():
            st.error("Journal name is required.")
        else:
            entry = JournalWhitelistEntry(
                name=add_name.strip(),
                group=add_group.strip() or None,
                issns=set(split_issns(add_issn)),
                issn_l=normalize_issn(add_issn),
                source="ui",
            )
            repository.upsert_whitelist([entry])
            st.success(f"Added {entry.name}.")
            st.rerun()
    if entries:
        remove_name = st.selectbox(
            "Remove journal",
            [entry.normalized_name for entry in entries],
            format_func=lambda value: next(
                entry.name for entry in entries if entry.normalized_name == value
            ),
        )
        if st.button("Remove selected journal"):
            repository.remove_whitelist(remove_name)
            st.success("Journal removed.")
            st.rerun()


def render_settings(
    settings: Settings,
    engine: Any,
    profile: ResearchProfile,
) -> None:
    st.header("Research Settings")
    st.subheader("Runtime configuration")
    st.table(
        [
            {"Setting": "Database", "Value": settings.database_url},
            {"Setting": "Cache directory", "Value": str(settings.cache_dir)},
            {"Setting": "Download directory", "Value": str(settings.download_dir)},
            {"Setting": "OpenAlex API key", "Value": _configured(settings.openalex_api_key)},
            {
                "Setting": "Semantic Scholar API key",
                "Value": _configured(settings.semantic_scholar_api_key),
            },
            {"Setting": "Crossref mailto", "Value": _configured(settings.crossref_mailto)},
            {"Setting": "Unpaywall email", "Value": _configured(settings.unpaywall_email)},
            {"Setting": "Max download bytes", "Value": str(settings.max_download_bytes)},
        ]
    )
    st.subheader("Keyword preset")
    preset_name = st.text_input("Preset name", value=profile.name)
    if st.button("Save current profile preset"):
        preset_id = SettingsRepository(engine).save_keyword_preset(
            preset_name,
            {
                "primary": list(profile.primary_keywords),
                "extended": list(profile.extended_keywords),
                "excluded": list(profile.excluded_keywords),
            },
        )
        st.success(f"Saved preset {preset_id}.")
    presets = [p for p in SettingsRepository(engine).list_keyword_presets() if not p.name.startswith("__system_")]
    if presets:
        st.dataframe(
            pd.DataFrame(
                [
                    {
                        "Name": item.name,
                        "Keywords": json.dumps(item.keywords, ensure_ascii=False),
                    }
                    for item in presets
                ]
            ),
            width="stretch",
            hide_index=True,
        )
    st.subheader("Search history")
    sessions = LibraryRepository(engine).recent_sessions(20)
    st.dataframe(
        pd.DataFrame(
            [
                {"ID": item["id"], "Query": item["query"], "Created": item["created_at"]}
                for item in sessions
            ]
        ),
        width="stretch",
        hide_index=True,
    )


def _render_library_row(row: LibraryPaper, selected_ids: set[int]) -> None:
    widget_key = f"paper_selected_{row.paper_id}"
    if widget_key not in st.session_state:
        st.session_state[widget_key] = row.paper_id in selected_ids
    columns = st.columns([0.05, 0.55, 0.18, 0.22])
    checked = columns[0].checkbox(
        "select",
        key=widget_key,
        label_visibility="collapsed",
    )
    if checked:
        selected_ids.add(row.paper_id)
    else:
        selected_ids.discard(row.paper_id)
    columns[1].markdown(f"**{row.paper.title}**")
    if row.paper.pdf_url or row.paper.oa_locations:
        columns[1].caption("PDF candidate available")
    elif row.paper.doi:
        columns[1].caption("No PDF in metadata · Unpaywall checked on download")
    else:
        columns[1].caption("No PDF URL available")
    columns[2].write(row.paper.journal_name or "Unknown journal")
    columns[3].write(
        f'{row.paper.publication_year or "?"} · '
        f'{row.paper.quartile.value} · '
        f'{row.paper.quality_bucket or "unfiltered"}'
    )
    with st.expander("Metadata", expanded=False):
        if row.paper.abstract:
            st.write(row.paper.abstract[:600])
        link_columns = st.columns(2)
        if row.paper.doi:
            link_columns[0].link_button(
                "Open DOI",
                f"https://doi.org/{row.paper.doi}",
            )
        if row.paper.landing_page_url:
            link_columns[1].link_button("Open landing page", row.paper.landing_page_url)
        st.write(
            {
                "Paper ID": row.paper_id,
                "Authors": row.paper.authors,
                "DOI": row.paper.doi,
                "Source": row.paper.metadata_sources,
                "Open access PDF": row.paper.pdf_url,
                "Relevance": row.paper.relevance_score,
                "Quality rule": row.paper.matched_rule,
            }
        )


def _download_rows(
    settings: Settings,
    engine: Any,
    rows: list[LibraryPaper],
) -> None:
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    progress = st.progress(0.0, text="Preparing download queue...")

    def on_progress(event: Any) -> None:
        fraction = event.completed / event.total if event.total else 1.0
        progress.progress(
            fraction,
            text=f"{event.completed}/{event.total}: {event.current_title}",
        )

    if not settings.unpaywall_email:
        st.caption(
            "Chưa cấu hình LAW_RESEARCH_UNPAYWALL_EMAIL: vẫn tìm PDF từ OpenAlex; "
            "thêm email để tăng khả năng tìm bản Open Access từ Unpaywall."
        )
    queue = _build_download_queue(settings)
    report = queue.download(
        [row.paper for row in rows],
        settings.download_dir,
        progress_callback=on_progress,
    )
    st.session_state["download_report"] = report
    download_repository = DownloadRepository(engine)
    for row, item in zip(rows, report.items):
        task_id = download_repository.create_task(
            row.paper_id,
            source_url=item.source_url,
            source=item.source,
        )
        download_repository.update_task(
            task_id,
            status=item.status,
            attempts=item.attempts,
            progress=1.0 if item.status is DownloadStatus.DOWNLOADED else 0.0,
            error_message=item.error,
        )
        if item.local_path and item.status is DownloadStatus.DOWNLOADED:
            download_repository.add_file(
                task_id,
                item.local_path,
                sha256=item.sha256,
                size_bytes=item.size_bytes,
            )
    if report.success_count:
        st.success(
            f"Download batch finished: {report.success_count}/{len(report.items)} successful."
        )
    else:
        st.error(
            f"Download batch finished: 0/{len(report.items)} successful. "
            "See the details below or open Download Manager."
        )
    _render_pdf_export_buttons(report, settings.download_dir)
    _render_download_results(report)


def _persist_retry_results(engine: Any, before: BatchDownloadReport, after: BatchDownloadReport) -> None:
    """Keep retry history durable without duplicating previous successes."""
    repository = DownloadRepository(engine)
    retried_statuses = {
        DownloadStatus.FAILED,
        DownloadStatus.INVALID_PDF,
        DownloadStatus.ACCESS_RESTRICTED,
    }
    for previous, current in zip(before.items, after.items):
        if previous.status not in retried_statuses:
            continue
        paper_id = repository.find_paper_id(current.paper)
        if paper_id is None:
            continue
        task_id = repository.create_task(
            paper_id, source_url=current.source_url, source=current.source
        )
        repository.update_task(
            task_id, status=current.status, attempts=current.attempts,
            progress=1.0 if current.status is DownloadStatus.DOWNLOADED else 0.0,
            error_message=current.error,
        )
        if current.status is DownloadStatus.DOWNLOADED and current.local_path:
            repository.add_file(
                task_id, current.local_path, sha256=current.sha256,
                size_bytes=current.size_bytes,
            )


def _render_saved_pdf_history(engine: Any, settings: Settings) -> None:
    """Browser downloads from prior SQLite history, not just the current session."""
    history = DownloadRepository(engine).list_history(limit=1000)
    if not history:
        st.info("Chưa có lịch sử tải PDF.")
        return
    st.dataframe(pd.DataFrame(history[:100]), width="stretch", hide_index=True)
    # A DB-stored file path is not authority to read arbitrary files on the server.
    base = settings.download_dir.resolve()
    shown: set[Path] = set()
    files: list[Path] = []
    for entry in history:
        if entry["status"] != DownloadStatus.DOWNLOADED.value or not entry["file"]:
            continue
        location = Path(str(entry["file"]).replace("\\", "/"))
        if not location.is_absolute():
            location = ROOT / location
        location = location.resolve()
        if location.is_relative_to(base) and location.is_file() and location not in shown:
            shown.add(location)
            files.append(location)
    if files:
        st.success(f"Có {len(files)} PDF từ các lần tải trước vẫn còn trên ổ đĩa.")
        if len(files) <= 30:
            for index, location in enumerate(files):
                st.download_button(
                    f"⬇️ {location.name[:100]}",
                    data=location.read_bytes(),
                    file_name=location.name,
                    mime="application/pdf",
                    key=f"saved_pdf_{index}",
                )
        else:
            st.caption("Có trên 30 file, chỉ hiển thị lịch sử để tránh tốn bộ nhớ.")
    else:
        st.caption("Lịch sử có trong SQLite nhưng các tệp PDF cũ không còn ở thư mục tải.")


def _render_pdf_export_buttons(report: BatchDownloadReport, output_dir: Path) -> None:
    """Server-side PDF save is not a browser download; show clear browser buttons."""
    downloadable = [
        item for item in report.downloaded
        if item.local_path is not None and item.local_path.is_file()
    ]
    if not downloadable:
        st.info(
            "Không có PDF tải được trong đợt này. Kiểm tra Status/Error bên dưới. "
            "Bài không có bản Open Access sẽ chỉ có đường dẫn trang bài báo."
        )
        return
    st.success(f"Có {len(downloadable)} PDF đã lưu trên máy chạy ứng dụng.")
    archive_path = export_zip(report, output_dir / "selected-papers.zip")
    st.download_button(
        "⬇️ Tải các PDF về máy của tôi (ZIP)",
        data=archive_path.read_bytes(),
        file_name="law-ai-research-pdfs.zip",
        mime="application/zip",
        key="browser_pdf_archive",
    )
    if len(downloadable) <= 20:
        for index, item in enumerate(downloadable):
            st.download_button(
                f"Tải PDF: {item.paper.title[:90]}",
                data=item.local_path.read_bytes(),
                file_name=item.local_path.name,
                mime="application/pdf",
                key=f"browser_pdf_{index}",
            )


def _render_download_results(report: BatchDownloadReport) -> None:
    st.subheader("Download details")
    st.dataframe(
        pd.DataFrame(
            [
                {
                    "Title": item.paper.title,
                    "Status": item.status.value,
                    "Source": item.source or "",
                    "Attempts": item.attempts,
                    "Error": item.error or (
                        "Downloaded successfully" if item.local_path else ""
                    ),
                    "Landing page": item.source_url or item.paper.landing_page_url or "",
                }
                for item in report.items
            ]
        ),
        width="stretch",
        hide_index=True,
    )
    restricted = [
        item for item in report.items if item.status is DownloadStatus.ACCESS_RESTRICTED
    ]
    if restricted:
        st.warning(
            f"Có {len(restricted)} bài chưa tải được (ACCESS_RESTRICTED). "
            "Nguyên nhân có thể là: chưa tìm được bản OA, đường dẫn PDF trả 403, "
            "hoặc dịch vụ tra cứu bị lỗi. Xem cột Error từng bài để phân biệt. "
            "Nếu vừa thêm email Unpaywall/API key OpenAlex vào .env, hãy khởi động lại "
            "Streamlit rồi chọn Retry failed. Ứng dụng không vượt paywall/CAPTCHA."
        )


def _build_clients(settings: Settings, sources: list[str]) -> dict[str, Any]:
    cache = JsonFileCache(settings.cache_dir, settings.cache_ttl_seconds)
    clients: dict[str, Any] = {}
    if "OpenAlex" in sources:
        clients["openalex"] = OpenAlexClient(
            email=settings.openalex_email,
            api_key=settings.openalex_api_key,
            timeout=settings.http_timeout_seconds,
            cache=cache,
        )
    if "Semantic Scholar" in sources:
        clients["semantic_scholar"] = SemanticScholarClient(
            api_key=settings.semantic_scholar_api_key,
            timeout=settings.http_timeout_seconds,
            cache=cache,
        )
    if "Crossref" in sources:
        clients["crossref"] = CrossrefClient(
            mailto=settings.crossref_mailto,
            timeout=settings.http_timeout_seconds,
            cache=cache,
        )
    return clients


def _build_download_queue(settings: Settings) -> DownloadQueue:
    unpaywall = (
        UnpaywallClient(
            email=settings.unpaywall_email,
            timeout=settings.http_timeout_seconds,
            cache=JsonFileCache(settings.cache_dir, settings.cache_ttl_seconds),
        )
        if settings.unpaywall_email
        else None
    )
    openalex = OpenAlexClient(
        email=settings.openalex_email,
        api_key=settings.openalex_api_key,
        timeout=settings.http_timeout_seconds,
        cache=JsonFileCache(settings.cache_dir, settings.cache_ttl_seconds),
        max_retries=1,
    )
    return DownloadQueue(
        FullTextResolver(unpaywall, openalex=openalex),
        PDFDownloader(
            max_bytes=settings.max_download_bytes,
            trust_env=settings.download_use_system_proxy,
        ),
    )


def _ensure_default_whitelist(repository: RankingRepository, profile: ResearchProfile) -> None:
    """Seed configuration on first use; preserve later deliberate DB edits."""
    marker_name = "__system_whitelist_initialized__"
    settings_repo = SettingsRepository(repository.engine)
    names = {preset.name for preset in settings_repo.list_keyword_presets()}
    if marker_name not in names:
        if not repository.list_whitelist():
            repository.upsert_whitelist(JournalWhitelist.from_profile(profile).entries)
        settings_repo.save_keyword_preset(marker_name, {"initialized": True})


def _load_sjr(
    uploaded_file: Any,
    ranking_year: int | None,
    subject: str,
) -> ScimagoCSVImporter:
    if uploaded_file is None:
        return ScimagoCSVImporter([])
    return ScimagoCSVImporter.from_text(
        uploaded_file.getvalue().decode("utf-8-sig"),
        ranking_year=ranking_year,
        subject=subject or None,
    )


def _render_source_errors() -> None:
    for source, error in st.session_state.get("source_errors", {}).items():
        st.warning(f"{source}: {error}")


def _lines(value: str) -> tuple[str, ...]:
    return tuple(line.strip() for line in value.splitlines() if line.strip())


def _configured(value: str | None) -> str:
    return "configured" if value else "not configured"


def _export_bytes(rows: list[LibraryPaper]) -> tuple[bytes, bytes]:
    frame = pd.DataFrame(
        [
            {
                "paper_id": row.paper_id,
                "doi": row.paper.doi or "",
                "title": row.paper.title,
                "authors": "; ".join(row.paper.authors),
                "year": row.paper.publication_year or "",
                "journal": row.paper.journal_name or "",
                "quartile": row.paper.quartile.value,
                "quality_rule": row.paper.matched_rule or "",
                "quality_bucket": row.paper.quality_bucket or "",
                "relevance_score": row.paper.relevance_score,
                "open_access_pdf": row.paper.pdf_url or "",
                "landing_page": row.paper.landing_page_url or "",
            }
            for row in rows
        ]
    )
    csv_bytes = frame.to_csv(index=False).encode("utf-8-sig")
    excel_buffer = io.BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name="Papers")
    return csv_bytes, excel_buffer.getvalue()


if __name__ == "__main__":
    main()
