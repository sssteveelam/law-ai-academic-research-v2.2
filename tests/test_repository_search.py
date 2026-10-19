from sqlalchemy import select
from sqlalchemy.orm import Session

from models.db import Paper, SearchResult, SearchSession
from models.domain import PaperRecord
from repositories.database import create_database_engine
from repositories.search import SearchRepository


def test_save_search_upserts_by_doi_and_persists_authors() -> None:
    engine = create_database_engine("sqlite:///:memory:")
    repository = SearchRepository(engine)
    first = PaperRecord(
        source_api="openalex",
        source_id="W1",
        doi="10.1000/shared",
        title="Shared Paper",
        authors=["Author A"],
        metadata_sources=["openalex"],
    )
    second = PaperRecord(
        source_api="crossref",
        source_id="10.1000/shared",
        doi="https://doi.org/10.1000/shared",
        title="Shared Paper",
        authors=["Author B"],
        metadata_sources=["crossref"],
    )
    first_session_id = repository.save_search("first", [first])
    second_session_id = repository.save_search("second", [second])

    with Session(engine) as session:
        assert session.scalar(select(SearchSession).where(SearchSession.id == first_session_id))
        assert session.scalar(select(SearchSession).where(SearchSession.id == second_session_id))
        assert session.scalar(select(SearchResult)) is not None
        papers = session.scalars(select(Paper)).all()
        assert len(papers) == 1
        assert papers[0].metadata_sources == ["openalex", "crossref"]
        assert {author.display_name for author in papers[0].authors} == {"Author A", "Author B"}
