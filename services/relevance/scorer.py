from __future__ import annotations

import re
from dataclasses import dataclass

from models.domain import PaperRecord


@dataclass(frozen=True)
class KeywordProfile:
    primary: tuple[str, ...] = ()
    extended: tuple[str, ...] = ()
    related: tuple[str, ...] = ()
    excluded: tuple[str, ...] = ()
    legal_terms: tuple[str, ...] = (
        "liability",
        "legal responsibility",
        "causation",
        "fault",
        "tort",
        "accountability",
    )

    def positive_terms(self) -> tuple[str, ...]:
        values = [
            *self.primary,
            *self.extended,
            *self.related,
            *self.legal_terms,
        ]
        return tuple(dict.fromkeys(term.strip() for term in values if term.strip()))


@dataclass(frozen=True)
class RelevanceResult:
    score: float
    matched_terms: tuple[str, ...]
    excluded_matches: tuple[str, ...]
    explanation: str


def score_paper(paper: PaperRecord, profile: KeywordProfile) -> RelevanceResult:
    positive = profile.positive_terms()
    title = _normalize(paper.title)
    abstract = _normalize(paper.abstract)
    keyword_text = _normalize(" ".join(paper.keywords))
    title_hits = _hits(positive, title)
    abstract_hits = _hits(positive, abstract)
    keyword_hits = _hits(positive, keyword_text)
    excluded_hits = _hits(profile.excluded, " ".join([title, abstract]))
    denominator = max(len(positive), 1)
    title_coverage = len(title_hits) / denominator
    abstract_coverage = len(abstract_hits) / denominator
    keyword_coverage = len(keyword_hits) / denominator
    score = 0.55 * title_coverage + 0.35 * abstract_coverage + 0.10 * keyword_coverage
    if excluded_hits:
        score *= 0.25
    score = round(min(max(score, 0.0), 1.0), 4)
    matched = tuple(dict.fromkeys([*title_hits, *abstract_hits, *keyword_hits]))
    explanation = (
        f"title={len(title_hits)}, abstract={len(abstract_hits)}, "
        f"keywords={len(keyword_hits)}"
    )
    if excluded_hits:
        explanation += f"; excluded={', '.join(excluded_hits)}"
    return RelevanceResult(score, matched, tuple(excluded_hits), explanation)


def apply_relevance(
    papers: list[PaperRecord], profile: KeywordProfile
) -> list[PaperRecord]:
    return [
        paper.model_copy(
            update={
                "relevance_score": result.score,
                "relevance_explanation": result.explanation,
            }
        )
        for paper in papers
        for result in [score_paper(paper, profile)]
    ]


def _normalize(value: str | None) -> str:
    return re.sub(r"\s+", " ", (value or "").lower()).strip()


def _hits(terms: tuple[str, ...], text: str) -> list[str]:
    return [term for term in terms if _phrase_match(term, text)]


def _phrase_match(term: str, text: str) -> bool:
    normalized = _normalize(term)
    if not normalized:
        return False
    return re.search(rf"(?<!\w){re.escape(normalized)}(?!\w)", text) is not None
