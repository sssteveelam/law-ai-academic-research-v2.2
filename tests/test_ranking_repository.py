from sqlalchemy import select
from sqlalchemy.orm import Session

from models.db import JournalRanking, TargetJournal
from repositories.database import create_database_engine
from repositories.ranking import RankingRepository
from services.ranking.scimago import ScimagoCSVImporter
from services.ranking.whitelist import JournalWhitelistEntry


def test_ranking_repository_persists_sjr_and_whitelist_identity() -> None:
    engine = create_database_engine("sqlite:///:memory:")
    rows = ScimagoCSVImporter.from_text(
        "Title,Issn,SJR Best Quartile,Year\nTrusted,1234-5678,Q1,2024\n"
    ).rows
    entries = [
        JournalWhitelistEntry(
            name="Trusted",
            issns={"1234-5678"},
            issn_l="1234-5678",
            aliases={"Trusted Journal"},
            group="Test",
        )
    ]
    repository = RankingRepository(engine)
    assert repository.replace_source_rows(rows) == 1
    assert repository.upsert_whitelist(entries) == 1

    with Session(engine) as session:
        ranking = session.scalar(select(JournalRanking))
        journal = session.scalar(select(TargetJournal))
        assert ranking is not None
        assert ranking.quartile == "Q1"
        assert journal is not None
        assert journal.issns == ["12345678"]
        assert journal.aliases == ["Trusted Journal"]
