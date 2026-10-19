from pathlib import Path

from models.domain import PaperRecord
from services.ranking.whitelist import JournalWhitelist, JournalWhitelistEntry
from services.search.planner import ResearchProfile


def test_whitelist_matches_issn_before_name() -> None:
    whitelist = JournalWhitelist(
        [
            JournalWhitelistEntry(
                name="Artificial Intelligence and Law",
                issns={"1234-5678"},
            )
        ]
    )
    paper = PaperRecord(
        source_api="test",
        source_id="1",
        title="Paper",
        journal_name="Artificial Intelligence and Law",
        issn=["12345678"],
    )
    match = whitelist.match(paper)
    assert match.matched is True
    assert match.method == "issn"


def test_known_issn_mismatch_does_not_false_positive_by_name() -> None:
    whitelist = JournalWhitelist(
        [
            JournalWhitelistEntry(
                name="Artificial Intelligence and Law",
                issns={"1234-5678"},
            )
        ]
    )
    paper = PaperRecord(
        source_api="test",
        source_id="2",
        title="Paper",
        journal_name="Artificial Intelligence and Law",
        issn=["9999-9999"],
    )
    assert whitelist.match(paper).matched is False


def test_whitelist_name_alias_is_exact_not_substring() -> None:
    whitelist = JournalWhitelist(
        [
            JournalWhitelistEntry(
                name="Law and Courts",
                aliases={"Journal of Law and Courts"},
            )
        ]
    )
    exact = PaperRecord(
        source_api="test",
        source_id="3",
        title="Paper",
        journal_name="Journal of Law and Courts",
    )
    false_positive = PaperRecord(
        source_api="test",
        source_id="4",
        title="Paper",
        journal_name="Law and Courts Review",
    )
    assert whitelist.match(exact).matched is True
    assert whitelist.match(false_positive).matched is False


def test_research_profile_contains_requested_target_journals() -> None:
    profile = ResearchProfile.from_file(Path("config/research_profile.json"))
    names = {item["name"] for item in profile.target_journals}
    expected = {
        "Stanford Law Review",
        "Duke Law Journal",
        "California Law Review",
        "Michigan Law Review",
        "Asia Pacific Law Review",
        "Journal of Law and Courts",
        "Artificial Intelligence and Law",
        "Asian Journal of Criminology",
        "Crime, Law and Social Change",
        "Criminal Law Forum",
        "Criminal Law and Philosophy",
        "Hague Journal on the Rule of Law",
        "European Journal of International Law",
        "European Competition Law Review",
        "European Intellectual Property Review",
        "Oxford University Commonwealth Law Journal",
        "International Journal of Transitional Justice",
        "Journal of International Law and International Relations",
        "Revue Lamy de la concurrence",
        "Revue Lamy droit civil",
        "Revue de droit international et de droit comparé",
        "Revue Propriété industrielle",
        "Harvard International Law Journal",
        "Virginia Journal of International Law",
        "Washington International Law Journal",
        "Yale Journal of International Law",
        "Berkeley Journal of International Law",
        "Boston University International Law Journal",
        "Chicago Journal of International Law",
        "Connecticut Journal of International Law",
        "Cornell International Law Journal",
        "Florida Journal of International Law",
        "The George Washington International Law Review",
        "North Carolina Journal of International Law and Commercial Regulation",
        "NYU Journal of International Law and Politics",
        "Texas International Law Journal",
    }

    assert expected <= names
