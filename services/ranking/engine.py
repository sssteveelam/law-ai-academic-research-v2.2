from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from models.domain import PaperRecord, Quartile
from services.ranking.scimago import RankingMatch, ScimagoCSVImporter
from services.ranking.whitelist import JournalWhitelist, WhitelistMatch


class ResearchMode(StrEnum):
    RECOMMENDED = "Recommended"
    BROAD = "Broad"
    CUSTOM = "Custom"


@dataclass(frozen=True)
class ResearchFilterConfig:
    mode: ResearchMode = ResearchMode.RECOMMENDED
    selected_quartiles: frozenset[Quartile] = frozenset()
    include_reference: bool = False
    ranking_year: int | None = None
    subject: str | None = None

    def effective_quartiles(self) -> frozenset[Quartile]:
        if self.mode is ResearchMode.RECOMMENDED:
            return frozenset({Quartile.Q1, Quartile.Q2})
        if self.mode is ResearchMode.BROAD:
            return frozenset({Quartile.Q1, Quartile.Q2, Quartile.Q3, Quartile.Q4})
        return self.selected_quartiles


@dataclass(frozen=True)
class PaperQualityDecision:
    paper: PaperRecord
    accepted: bool
    bucket: str
    rule: str
    quartile_match: bool
    whitelist_match: bool
    ranking: RankingMatch
    whitelist: WhitelistMatch


@dataclass(frozen=True)
class QualityFilterResult:
    priority: list[PaperRecord]
    reference: list[PaperRecord]
    excluded: list[PaperRecord]

    @property
    def accepted(self) -> list[PaperRecord]:
        return [*self.priority, *self.reference]


def evaluate_paper(
    paper: PaperRecord,
    ranking: ScimagoCSVImporter,
    whitelist: JournalWhitelist,
    config: ResearchFilterConfig,
) -> PaperQualityDecision:
    ranking_match = ranking.match(
        journal_name=paper.journal_name,
        issns=paper.issn,
        ranking_year=config.ranking_year,
        subject=config.subject,
    )
    whitelist_match = whitelist.match(paper)
    enriched = paper.model_copy(
        update={
            "quartile": ranking_match.quartile,
            "quartile_year": ranking_match.ranking_year,
            "ranking_source": ranking_match.source,
            "ranking_subject": ranking_match.subject,
            "whitelist_matched": whitelist_match.matched,
            "journal_match_method": whitelist_match.method,
        }
    )
    quartile_match = ranking_match.quartile in config.effective_quartiles()
    priority = quartile_match or whitelist_match.matched
    reference = (
        config.mode is ResearchMode.RECOMMENDED
        and config.include_reference
        and ranking_match.quartile in {Quartile.Q3, Quartile.Q4}
        and not priority
    )
    if quartile_match and whitelist_match.matched:
        rule = "BOTH"
    elif quartile_match:
        rule = "QUARTILE"
    elif whitelist_match.matched:
        rule = "WHITELIST"
    elif reference:
        rule = "REFERENCE"
    else:
        rule = "NONE"
    bucket = "priority" if priority else "reference" if reference else "excluded"
    enriched = enriched.model_copy(
        update={
            "matched_rule": rule,
            "quality_accepted": priority or reference,
            "quality_bucket": bucket,
        }
    )
    return PaperQualityDecision(
        paper=enriched,
        accepted=priority or reference,
        bucket=bucket,
        rule=rule,
        quartile_match=quartile_match,
        whitelist_match=whitelist_match,
        ranking=ranking_match,
        whitelist=whitelist_match,
    )


def filter_papers(
    papers: list[PaperRecord],
    ranking: ScimagoCSVImporter,
    whitelist: JournalWhitelist,
    config: ResearchFilterConfig,
) -> QualityFilterResult:
    priority: list[PaperRecord] = []
    reference: list[PaperRecord] = []
    excluded: list[PaperRecord] = []
    for paper in papers:
        decision = evaluate_paper(paper, ranking, whitelist, config)
        if decision.bucket == "priority":
            priority.append(decision.paper)
        elif decision.bucket == "reference":
            reference.append(decision.paper)
        else:
            excluded.append(decision.paper)
    return QualityFilterResult(priority, reference, excluded)
