"""New network-free regression coverage for backend + PDF downloader fixes."""
from pathlib import Path

import httpx
import pytest

from models.domain import DownloadStatus, PaperRecord, Quartile
from repositories.database import create_database_engine
from repositories.ranking import RankingRepository
from services.fulltext.downloader import DownloadFailure, PDFDownloader
from services.fulltext.queue import DownloadQueue, export_zip
from services.fulltext.resolver import FullTextResolver
from services.fulltext.security import UnsafeURL, validate_public_dns_host
from services.ranking.engine import ResearchFilterConfig, evaluate_paper
from services.ranking.scimago import ScimagoCSVImporter
from services.ranking.whitelist import JournalWhitelistEntry
from services.search.normalization import deduplicate_papers

PDF = b"%PDF-1.4\n1 0 obj\n<<>>\nendobj\n%%EOF\n"


def make_paper(title: str, doi: str | None = None, year: int | None = None,
               url: str | None = None, journal: str | None = None) -> PaperRecord:
    return PaperRecord(source_api="test", source_id=title, title=title,
                       doi=doi, publication_year=year, pdf_url=url,
                       journal_name=journal)


def mock_client(handler):
    return httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True)


def test_persisted_ranking_and_whitelist_used_by_quality_engine():
    engine = create_database_engine("sqlite:///:memory:")
    repo = RankingRepository(engine)
    ranking = ScimagoCSVImporter.from_text(
        "Title,Issn,SJR Best Quartile,Year\nLaw & AI,1234-5678,Q1,2025\n"
    )
    repo.replace_source_rows(ranking.rows)
    repo.upsert_whitelist([
        JournalWhitelistEntry(name="Listed Law", enabled=True, issns={"2345-6789"},
                              aliases={"LL Review"}),
        JournalWhitelistEntry(name="Disabled Law", enabled=False),
    ])
    restored = repo.load_rankings()
    whitelist = repo.load_whitelist()
    quality = evaluate_paper(make_paper("Paper", year=2024, journal="Law & AI").model_copy(
        update={"issn": ["1234-5678"]}), restored, whitelist, ResearchFilterConfig())
    assert quality.paper.quartile is Quartile.Q1
    assert quality.paper.quartile_year == 2025
    assert quality.rule == "QUARTILE"
    assert evaluate_paper(make_paper("P", journal="LL Review"), restored, whitelist,
                          ResearchFilterConfig()).rule == "WHITELIST"
    assert not whitelist.match(make_paper("P", journal="Disabled Law")).matched
    repo.remove_whitelist("listed law")
    assert not repo.load_whitelist().match(make_paper("P", journal="LL Review")).matched


def test_ranking_undated_when_requested_year_and_latest_when_unselected():
    ranking = ScimagoCSVImporter.from_text(
        "Title,Issn,SJR Best Quartile,Year\nJournal A,1234-5678,Q2,2023\n"
        "Journal A,1234-5678,Q1,2025\n"
    )
    assert ranking.match(journal_name="Journal A", issns=["1234-5678"]).quartile is Quartile.Q1
    assert ranking.match(journal_name="Journal A", issns=["1234-5678"], ranking_year=2024).quartile is Quartile.UNKNOWN
    undated = ScimagoCSVImporter.from_text("Title,Issn,SJR Best Quartile\nJournal B,1234-5678,Q1\n")
    match = undated.match(journal_name="Journal B", issns=["1234-5678"], ranking_year=2024)
    assert match.quartile is Quartile.Q1
    assert match.ranking_year is None


def test_dedup_known_and_unknown_doi_without_conflating_conflicting_dois():
    papers = [
        make_paper("The Limits of Algorithmic Liability", "10.1/a", 2024),
        make_paper("The Limits of Algorithmic Liability", None, 2024),
    ]
    assert len(deduplicate_papers(papers)) == 1
    papers.append(make_paper("The Limits of Algorithmic Liability", "10.1/b", 2024))
    assert len(deduplicate_papers(papers)) == 2


def test_redirect_private_ip_is_never_requested(tmp_path: Path):
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(302, headers={"location": "http://127.0.0.1/secret.pdf"}, request=request)

    downloader = PDFDownloader(client=mock_client(handler))
    with pytest.raises(DownloadFailure):
        downloader.download("https://repository.example/redirect", tmp_path / "file.pdf")
    assert requested == ["https://repository.example/redirect"]
    assert not (tmp_path / "file.pdf").exists()


def test_dns_blocks_internal_answer_before_network(monkeypatch):
    import socket
    monkeypatch.setattr(socket, "getaddrinfo", lambda *args, **kwargs: [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.7", 0))
    ])
    with pytest.raises(UnsafeURL):
        validate_public_dns_host("https://research-host.example/paper.pdf")


def test_oversized_stream_is_aborted_and_temp_cleaned(tmp_path: Path):
    def handler(request):
        return httpx.Response(200, content=b"%PDF-" + b"a" * 1000,
                              headers={"content-type": "application/pdf"}, request=request)
    downloader = PDFDownloader(client=mock_client(handler), max_bytes=50)
    dest = tmp_path / "paper.pdf"
    with pytest.raises(DownloadFailure) as exc:
        downloader.download("https://repository.example/a.pdf", dest)
    assert exc.value.invalid_pdf
    assert not dest.exists()
    assert not (tmp_path / "paper.pdf.part").exists()


def test_retry_keeps_previous_success_and_complete_zip(tmp_path: Path):
    requests = []

    def handler(request):
        requests.append(request.url.path)
        if request.url.path.endswith("b.pdf") and requests.count("/b.pdf") == 1:
            raise httpx.ConnectError("temporary", request=request)
        return httpx.Response(200, content=PDF, headers={"content-type": "application/pdf"}, request=request)

    queue = DownloadQueue(FullTextResolver(), PDFDownloader(client=mock_client(handler)), max_attempts=1)
    papers = [make_paper("A", url="https://repository.example/a.pdf"),
              make_paper("B", url="https://repository.example/b.pdf")]
    first = queue.download(papers, tmp_path)
    assert first.success_count == 1
    recovered = queue.retry_failed(first, tmp_path)
    assert recovered.success_count == 2
    assert [item.paper.title for item in recovered.items] == ["A", "B"]
    assert requests.count("/a.pdf") == 1
    archive = export_zip(recovered, tmp_path / "batch.zip")
    import zipfile
    with zipfile.ZipFile(archive) as z:
        assert set(z.namelist()) == {"A.pdf"}  # identical PDFs deduped by SHA256


def test_conflicting_duplicate_sjr_import_keeps_unknown_instead_of_crashing():
    engine = create_database_engine("sqlite:///:memory:")
    repo = RankingRepository(engine)
    duplicate = ScimagoCSVImporter.from_text(
        "Title,Issn,SJR Best Quartile,Year,Subject\n"
        "Journal A,1234-5678,Q1,2024,Law\n"
        "Journal A,1234-5678,Q2,2024,Law\n"
    )
    assert repo.replace_source_rows(duplicate.rows) == 2
    assert repo.load_rankings().match(journal_name="Journal A", issns=["1234-5678"]).quartile is Quartile.UNKNOWN


def test_download_history_persists_and_can_be_reloaded():
    from sqlalchemy.orm import Session
    from models.db import Paper
    from repositories.downloads import DownloadRepository

    engine = create_database_engine("sqlite:///:memory:")
    with Session(engine) as session:
        session.add(Paper(title="Existing", source_api="test", source_id="Existing"))
        session.commit()
    repo = DownloadRepository(engine)
    paper_id = repo.find_paper_id(make_paper("Existing"))
    assert paper_id is not None
    task_id = repo.create_task(paper_id, source_url="https://repository.example/pdf", source="repository")
    repo.update_task(task_id, status=DownloadStatus.DOWNLOADED, attempts=2, progress=1.0)
    history = repo.list_history()
    assert history[0]["title"] == "Existing"
    assert history[0]["attempts"] == 2
    assert history[0]["status"] == "DOWNLOADED"
