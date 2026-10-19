from models.domain import PaperRecord
from services.relevance.scorer import KeywordProfile, score_paper


def test_relevance_score_is_deterministic_and_explainable() -> None:
    profile = KeywordProfile(
        primary=("fault", "causation"),
        extended=("AI liability",),
        excluded=("medical imaging",),
    )
    paper = PaperRecord(
        source_api="test",
        source_id="1",
        title="Fault and AI liability",
        abstract="This article studies causation and legal responsibility.",
        keywords=["algorithmic accountability"],
    )
    result = score_paper(paper, profile)
    assert result.score > 0
    assert "fault" in result.matched_terms
    assert "title=" in result.explanation


def test_excluded_term_penalizes_score() -> None:
    profile = KeywordProfile(primary=("fault",), excluded=("medical imaging",))
    clean = PaperRecord(source_api="test", source_id="1", title="Fault liability")
    excluded = PaperRecord(
        source_api="test",
        source_id="2",
        title="Fault liability in medical imaging",
    )
    clean_score = score_paper(clean, profile)
    excluded_score = score_paper(excluded, profile)
    assert excluded_score.score < clean_score.score
    assert excluded_score.excluded_matches == ("medical imaging",)
