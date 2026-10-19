from models.domain import Quartile
from services.ranking.scimago import ScimagoCSVImporter

CSV = """Title,Issn,SJR Best Quartile,Year,Subject Area and Category
Trusted Journal,1234-5678,Q1,2024,Law
Reference Journal,2345-6789,Q3,2024,Law
Unranked Journal,3456-7890,Unranked,2024,Law
"""


def test_scimago_import_and_issn_matching() -> None:
    index = ScimagoCSVImporter.from_text(CSV)
    match = index.match(
        journal_name="Trusted Journal",
        issns=["1234 5678"],
        ranking_year=2024,
        subject="Law",
    )
    assert match.quartile is Quartile.Q1
    assert match.ranking_year == 2024
    assert match.method == "issn"


def test_wrong_issn_does_not_fall_back_to_same_name() -> None:
    index = ScimagoCSVImporter.from_text(CSV)
    match = index.match(
        journal_name="Trusted Journal",
        issns=["9999-9999"],
        ranking_year=2024,
        subject="Law",
    )
    assert match.quartile is Quartile.UNKNOWN


def test_year_or_subject_mismatch_is_unknown() -> None:
    index = ScimagoCSVImporter.from_text(CSV)
    assert (
        index.match(
            journal_name="Trusted Journal",
            issns=["1234-5678"],
            ranking_year=2023,
            subject="Law",
        ).quartile
        is Quartile.UNKNOWN
    )
    assert (
        index.match(
            journal_name="Trusted Journal",
            issns=["1234-5678"],
            ranking_year=2024,
            subject="Criminology",
        ).quartile
        is Quartile.UNKNOWN
    )
