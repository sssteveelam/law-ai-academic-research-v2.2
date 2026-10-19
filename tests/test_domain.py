from models.domain import OpenAccessStatus, PaperRecord


def test_paper_normalizes_doi_and_rejects_empty_title() -> None:
    paper = PaperRecord(
        source_api="test",
        source_id="1",
        doi="https://doi.org/10.1234/ABC",
        title="  A   useful paper  ",
    )
    assert paper.doi == "10.1234/abc"
    assert paper.title == "A useful paper"
    assert paper.open_access_status is OpenAccessStatus.UNKNOWN
