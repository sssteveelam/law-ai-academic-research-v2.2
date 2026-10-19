from models.domain import PaperRecord
from services.search.normalization import deduplicate_papers


def record(source: str, source_id: str, *, doi: str | None, title: str, author: str) -> PaperRecord:
    return PaperRecord(
        source_api=source,
        source_id=source_id,
        doi=doi,
        title=title,
        authors=[author],
        metadata_sources=[source],
        external_ids={source: source_id},
    )


def test_deduplicates_doi_and_merges_provenance() -> None:
    papers = deduplicate_papers(
        [
            record("openalex", "W1", doi="10.1000/x", title="Same Work", author="A"),
            record(
                "crossref",
                "10.1000/x",
                doi="https://doi.org/10.1000/X",
                title="Same Work",
                author="B",
            ),
        ]
    )
    assert len(papers) == 1
    assert papers[0].authors == ["A", "B"]
    assert papers[0].metadata_sources == ["openalex", "crossref"]


def test_same_title_with_different_dois_is_not_merged() -> None:
    papers = deduplicate_papers(
        [
            record("one", "1", doi="10.1000/one", title="Identical Title", author="A"),
            record("two", "2", doi="10.1000/two", title="Identical Title", author="B"),
        ]
    )
    assert len(papers) == 2


def test_no_doi_exact_title_is_conservative_fallback() -> None:
    papers = deduplicate_papers(
        [
            record("one", "1", doi=None, title="Causation in AI", author="A"),
            record("two", "2", doi=None, title="Causation in AI", author="B"),
        ]
    )
    assert len(papers) == 1


def test_no_doi_fuzzy_title_uses_explicit_threshold() -> None:
    papers = deduplicate_papers(
        [
            record("one", "1", doi=None, title="AI liability and fault", author="A"),
            record("two", "2", doi=None, title="AI liability and fault.", author="B"),
        ]
    )
    assert len(papers) == 1
