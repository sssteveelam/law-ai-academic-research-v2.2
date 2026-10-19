from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from models.domain import Quartile
from services.ranking.identifiers import (
    normalize_issn,
    normalize_journal_name,
    split_issns,
)


@dataclass(frozen=True)
class ScimagoRow:
    journal_name: str
    issns: tuple[str, ...]
    issn_l: str | None
    quartile: Quartile
    ranking_year: int | None
    subject: str | None
    source: str = "SCImago SJR"


@dataclass(frozen=True)
class RankingMatch:
    quartile: Quartile
    ranking_year: int | None
    subject: str | None
    source: str | None
    method: str | None


class ScimagoCSVImporter:
    """Import SJR CSV exports without inferring ranking facts."""

    def __init__(self, rows: list[ScimagoRow]) -> None:
        self.rows = rows

    @classmethod
    def from_path(
        cls,
        path: Path,
        *,
        ranking_year: int | None = None,
        subject: str | None = None,
    ) -> ScimagoCSVImporter:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            return cls.from_file(handle, ranking_year=ranking_year, subject=subject)

    @classmethod
    def from_text(
        cls,
        text: str,
        *,
        ranking_year: int | None = None,
        subject: str | None = None,
    ) -> ScimagoCSVImporter:
        return cls.from_file(
            io.StringIO(text), ranking_year=ranking_year, subject=subject
        )

    @classmethod
    def from_file(
        cls,
        handle: TextIO,
        *,
        ranking_year: int | None = None,
        subject: str | None = None,
    ) -> ScimagoCSVImporter:
        sample = handle.read(4096)
        handle.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(handle, dialect=dialect)
        headers = {cls._header_key(name): name for name in (reader.fieldnames or [])}
        journal_column = cls._find(headers, "title", "journal", "source title")
        issn_column = cls._find(headers, "issn", "issns")
        issn_l_column = cls._find(headers, "issnl", "linking issn", "issn l")
        quartile_column = cls._find(
            headers, "sjr best quartile", "best quartile", "quartile"
        )
        year_column = cls._find(headers, "year", "ranking year", "rank year")
        subject_column = cls._find(
            headers, "subject area and category", "subject", "category"
        )
        if not journal_column:
            raise ValueError("SCImago CSV must contain a journal/title column")
        if not quartile_column:
            raise ValueError("SCImago CSV must contain an SJR quartile column")
        rows: list[ScimagoRow] = []
        for raw in reader:
            name = (raw.get(journal_column) or "").strip()
            if not name:
                continue
            row_year = (_parse_year(raw.get(year_column)) or ranking_year) if year_column else ranking_year
            row_subject = (
                (raw.get(subject_column) or "").strip() or subject
                if subject_column
                else subject
            )
            row_issns = split_issns(raw.get(issn_column)) if issn_column else []
            row_issn_l = (
                normalize_issn(raw.get(issn_l_column)) if issn_l_column else None
            )
            rows.append(
                ScimagoRow(
                    journal_name=name,
                    issns=tuple(row_issns),
                    issn_l=row_issn_l,
                    quartile=_parse_quartile(raw.get(quartile_column)),
                    ranking_year=row_year,
                    subject=row_subject,
                )
            )
        return cls(rows)

    def match(
        self,
        *,
        journal_name: str | None,
        issns: list[str],
        ranking_year: int | None = None,
        subject: str | None = None,
    ) -> RankingMatch:
        normalized_issns = {
            value
            for value in (normalize_issn(item) for item in issns)
            if value
        }
        candidates: list[tuple[ScimagoRow, str]] = []
        if normalized_issns:
            for row in self.rows:
                identifiers = set(row.issns)
                if row.issn_l:
                    identifiers.add(row.issn_l)
                if normalized_issns.intersection(identifiers):
                    candidates.append((row, "issn"))
        else:
            normalized_name = normalize_journal_name(journal_name)
            if normalized_name:
                candidates = [
                    (row, "name")
                    for row in self.rows
                    if normalize_journal_name(row.journal_name) == normalized_name
                ]
        candidates = _filter_ranking_context(candidates, ranking_year, subject)
        if not candidates:
            return RankingMatch(Quartile.UNKNOWN, None, None, None, None)
        quartiles = {row.quartile for row, _ in candidates}
        if len(quartiles) != 1:
            return RankingMatch(Quartile.UNKNOWN, None, None, None, None)
        row, method = candidates[0]
        return RankingMatch(
            row.quartile,
            row.ranking_year,
            row.subject,
            row.source,
            method,
        )

    def as_rows(self) -> list[ScimagoRow]:
        return list(self.rows)

    @staticmethod
    def _header_key(value: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()

    @classmethod
    def _find(cls, headers: dict[str, str], *names: str) -> str | None:
        normalized = {cls._header_key(name) for name in names}
        for key, original in headers.items():
            if key in normalized:
                return original
        return None


def _filter_ranking_context(
    candidates: list[tuple[ScimagoRow, str]],
    ranking_year: int | None,
    subject: str | None,
) -> list[tuple[ScimagoRow, str]]:
    if subject:
        normalized_subject = normalize_journal_name(subject)
        candidates = [
            item for item in candidates
            if normalize_journal_name(item[0].subject) == normalized_subject
        ]
    if ranking_year is not None:
        # Prefer explicitly matching edition, then undated data; never use a
        # different dated edition to satisfy an explicitly requested year.
        exact = [item for item in candidates if item[0].ranking_year == ranking_year]
        candidates = exact or [item for item in candidates if item[0].ranking_year is None]
    elif candidates:
        # No ranking-year selected: choose the latest edition *in this subject*.
        # Publication year and ranking edition are not the same concept.
        dated = [item for item in candidates if item[0].ranking_year is not None]
        if dated:
            latest = max(item[0].ranking_year for item in dated)
            candidates = [item for item in dated if item[0].ranking_year == latest]
    return candidates


def _parse_year(value: str | None) -> int | None:
    if not value:
        return None
    match = re.search(r"\b(19|20)\d{2}\b", value)
    return int(match.group(0)) if match else None


def _parse_quartile(value: str | None) -> Quartile:
    if not value:
        return Quartile.UNKNOWN
    upper = value.upper()
    match = re.search(r"\bQ([1-4])\b", upper)
    if match:
        return Quartile(f"Q{match.group(1)}")
    if "UNRANKED" in upper:
        return Quartile.UNRANKED
    return Quartile.UNKNOWN
