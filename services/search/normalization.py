from __future__ import annotations

import re
import unicodedata
from difflib import SequenceMatcher

from models.domain import OpenAccessStatus, PaperRecord
from services.ranking.identifiers import normalize_journal_name


def normalize_title(value: str | None) -> str:
    if not value:
        return ""
    value = unicodedata.normalize("NFKD", value)
    value = "".join(char for char in value if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def normalize_issn(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"[^0-9Xx]", "", value).upper()
    return cleaned if len(cleaned) == 8 else None


def _is_better(candidate: object, current: object) -> bool:
    return bool(candidate) and not bool(current)


def merge_papers(left: PaperRecord, right: PaperRecord) -> PaperRecord:
    """Merge complementary metadata while retaining source provenance."""
    values = left.model_dump()
    for field in (
        "doi",
        "abstract",
        "publication_year",
        "publication_date",
        "journal_name",
        "publisher",
        "citation_count",
        "pdf_url",
        "landing_page_url",
    ):
        if _is_better(getattr(right, field), getattr(left, field)):
            values[field] = getattr(right, field)
    values["authors"] = list(dict.fromkeys([*left.authors, *right.authors]))
    values["keywords"] = list(dict.fromkeys([*left.keywords, *right.keywords]))
    values["oa_locations"] = list(
        dict.fromkeys([*left.oa_locations, *right.oa_locations])
    )
    values["issn"] = list(dict.fromkeys([*left.issn, *right.issn]))
    values["external_ids"] = {**left.external_ids, **right.external_ids}
    values["metadata_sources"] = list(
        dict.fromkeys([*left.metadata_sources, *right.metadata_sources])
    )
    if left.open_access_status is OpenAccessStatus.UNKNOWN:
        values["open_access_status"] = right.open_access_status
    if left.quartile.value == "Unknown" and right.quartile.value != "Unknown":
        values["quartile"] = right.quartile
        values["quartile_year"] = right.quartile_year
    return PaperRecord.model_validate(values)


def deduplicate_papers(papers: list[PaperRecord]) -> list[PaperRecord]:
    """Deduplicate by DOI/identifiers, then conservative no-DOI title matching."""
    result: list[PaperRecord] = []
    doi_index: dict[str, int] = {}
    identifier_index: dict[tuple[str, str], int] = {}
    for paper in papers:
        match_index: int | None = None
        if paper.doi:
            match_index = doi_index.get(paper.doi)
        if match_index is None:
            for key, value in paper.external_ids.items():
                if value:
                    match_index = identifier_index.get((key.lower(), value))
                    if match_index is not None:
                        break
        if match_index is None:
            title = normalize_title(paper.title)
            for index, existing in enumerate(result):
                if (
                    paper.publication_year
                    and existing.publication_year
                    and paper.publication_year != existing.publication_year
                ):
                    continue
                # Avoid merging different journals which reuse generic titles.
                if (
                    paper.journal_name and existing.journal_name
                    and normalize_journal_name(paper.journal_name)
                    != normalize_journal_name(existing.journal_name)
                ):
                    continue
                # Never merge two conflicting known DOIs on title alone.
                if paper.doi and existing.doi and paper.doi != existing.doi:
                    continue
                if (
                    title
                    and SequenceMatcher(
                        None, title, normalize_title(existing.title)
                    ).ratio()
                    >= 0.96
                ):
                    match_index = index
                    break
        if match_index is None:
            match_index = len(result)
            result.append(paper)
        else:
            result[match_index] = merge_papers(result[match_index], paper)
        merged = result[match_index]
        if merged.doi:
            doi_index[merged.doi] = match_index
        for key, value in merged.external_ids.items():
            if value:
                identifier_index[(key.lower(), value)] = match_index
    return result
