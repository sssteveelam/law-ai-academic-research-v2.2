from models.domain import PaperRecord, Quartile
from services.ranking.engine import (
    ResearchFilterConfig,
    ResearchMode,
    filter_papers,
)
from services.ranking.scimago import ScimagoCSVImporter
from services.ranking.whitelist import JournalWhitelist, JournalWhitelistEntry

CSV = """Title,Issn,SJR Best Quartile,Year,Subject
Q1 Journal,1111-1111,Q1,2024,Law
Q3 Journal,2222-2222,Q3,2024,Law
Unranked Journal,3333-3333,Unranked,2024,Law
"""


def make_paper(title: str, journal: str, issn: str) -> PaperRecord:
    return PaperRecord(
        source_api="test",
        source_id=title,
        title=title,
        journal_name=journal,
        issn=[issn],
        publication_year=2024,
    )


def test_q1_without_whitelist_is_accepted_by_or_rule() -> None:
    result = filter_papers(
        [make_paper("q1", "Q1 Journal", "1111-1111")],
        ScimagoCSVImporter.from_text(CSV),
        JournalWhitelist(),
        ResearchFilterConfig(),
    )
    assert len(result.priority) == 1
    assert result.priority[0].quartile is Quartile.Q1
    assert result.priority[0].matched_rule == "QUARTILE"


def test_unranked_whitelist_is_accepted() -> None:
    whitelist = JournalWhitelist(
        [JournalWhitelistEntry(name="Unranked Journal", issns={"3333-3333"})]
    )
    result = filter_papers(
        [make_paper("unranked", "Unranked Journal", "3333-3333")],
        ScimagoCSVImporter.from_text(CSV),
        whitelist,
        ResearchFilterConfig(),
    )
    assert len(result.priority) == 1
    assert result.priority[0].quartile is Quartile.UNRANKED
    assert result.priority[0].matched_rule == "WHITELIST"


def test_q3_changes_by_mode_and_reference_setting() -> None:
    paper = [make_paper("q3", "Q3 Journal", "2222-2222")]
    ranking = ScimagoCSVImporter.from_text(CSV)
    whitelist = JournalWhitelist()

    recommended = filter_papers(paper, ranking, whitelist, ResearchFilterConfig())
    assert not recommended.priority
    assert not recommended.reference
    assert len(recommended.excluded) == 1

    reference = filter_papers(
        paper,
        ranking,
        whitelist,
        ResearchFilterConfig(include_reference=True),
    )
    assert len(reference.reference) == 1
    assert reference.reference[0].matched_rule == "REFERENCE"

    broad = filter_papers(
        paper,
        ranking,
        whitelist,
        ResearchFilterConfig(mode=ResearchMode.BROAD),
    )
    assert len(broad.priority) == 1

    custom = filter_papers(
        paper,
        ranking,
        whitelist,
        ResearchFilterConfig(
            mode=ResearchMode.CUSTOM,
            selected_quartiles=frozenset({Quartile.Q3}),
        ),
    )
    assert len(custom.priority) == 1
