from models.domain import PaperRecord
from services.search.retrieval import filter_papers_by_journals, search_sources


def paper(source: str) -> PaperRecord:
    return PaperRecord(
        source_api=source,
        source_id=source,
        doi=f"10.1000/{source}",
        title=f"Paper from {source}",
    )


class GoodClient:
    def search(self, query: str, **kwargs):
        return [paper("openalex")]


class FailingClient:
    def search(self, query: str, **kwargs):
        raise RuntimeError("temporary failure")


def test_search_sources_isolates_failure() -> None:
    report = search_sources(
        {"openalex": GoodClient(), "crossref": FailingClient()},
        "liability",
    )
    assert len(report.papers) == 1
    assert report.source_counts == {"openalex": 1, "crossref": 0}
    assert "crossref" in report.source_errors


def test_filter_papers_by_journals_matches_normalized_names() -> None:
    papers = [
        PaperRecord(
            source_api="openalex",
            source_id="1",
            title="French journal paper",
            journal_name="Revue Propriété industrielle",
        ),
        PaperRecord(
            source_api="crossref",
            source_id="2",
            title="Other paper",
            journal_name="Other Journal",
        ),
    ]

    filtered = filter_papers_by_journals(papers, ["Revue Propriete industrielle"])

    assert [paper.source_id for paper in filtered] == ["1"]


def test_empty_journal_selection_keeps_all_papers() -> None:
    papers = [paper("openalex"), paper("crossref")]

    assert filter_papers_by_journals(papers, []) == papers
