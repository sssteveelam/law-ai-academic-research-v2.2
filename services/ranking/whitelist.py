from __future__ import annotations

import csv
import io
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from models.domain import PaperRecord
from services.ranking.identifiers import (
    normalize_issn,
    normalize_journal_name,
    split_issns,
)


@dataclass(frozen=True)
class WhitelistMatch:
    matched: bool
    method: str | None = None
    journal_name: str | None = None


@dataclass
class JournalWhitelistEntry:
    name: str
    group: str | None = None
    issns: set[str] = field(default_factory=set)
    issn_l: str | None = None
    aliases: set[str] = field(default_factory=set)
    enabled: bool = True
    source: str | None = None
    updated_at: datetime | None = None

    @property
    def normalized_name(self) -> str:
        return normalize_journal_name(self.name)

    @property
    def normalized_aliases(self) -> set[str]:
        return {normalize_journal_name(alias) for alias in self.aliases if alias}

    @property
    def identifiers(self) -> set[str]:
        values = set(self.issns)
        if self.issn_l:
            values.add(self.issn_l)
        return {value for value in (normalize_issn(v) for v in values) if value}


class JournalWhitelist:
    def __init__(self, entries: list[JournalWhitelistEntry] | None = None) -> None:
        self.entries = entries or []

    @classmethod
    def from_profile(cls, profile: Any) -> JournalWhitelist:
        entries = []
        for item in profile.target_journals:
            if isinstance(item, str):
                entries.append(JournalWhitelistEntry(name=item))
            else:
                entries.append(
                    JournalWhitelistEntry(
                        name=item["name"],
                        group=item.get("group"),
                        source="research_profile.json",
                    )
                )
        return cls(entries)

    @classmethod
    def from_csv_text(cls, text: str) -> JournalWhitelist:
        handle = io.StringIO(text)
        reader = csv.DictReader(handle)
        headers = {key.lower().strip(): key for key in (reader.fieldnames or [])}
        name_column = _find_header(headers, "name", "journal", "journal name", "title")
        if not name_column:
            raise ValueError("Whitelist CSV must contain a journal/name column")
        entries: list[JournalWhitelistEntry] = []
        for row in reader:
            name = (row.get(name_column) or "").strip()
            if not name:
                continue
            issn = _find_value(row, headers, "issn", "issns")
            issn_l = _find_value(row, headers, "issn-l", "issnl", "linking issn")
            aliases = _find_value(row, headers, "aliases", "alias")
            enabled_value = _find_value(row, headers, "enabled")
            entries.append(
                JournalWhitelistEntry(
                    name=name,
                    group=_find_value(row, headers, "group", "group name"),
                    issns=set(split_issns(issn)),
                    issn_l=normalize_issn(issn_l),
                    aliases=set(
                        alias.strip() for alias in (aliases or "").split("|") if alias.strip()
                    ),
                    enabled=enabled_value.lower() not in {"0", "false", "no"}
                    if enabled_value
                    else True,
                    source="csv",
                )
            )
        return cls(entries)

    @classmethod
    def from_csv_path(cls, path: Path) -> JournalWhitelist:
        return cls.from_csv_text(path.read_text(encoding="utf-8-sig"))

    def match(self, paper: PaperRecord) -> WhitelistMatch:
        paper_issns = {
            value
            for value in (normalize_issn(item) for item in paper.issn)
            if value
        }
        paper_name = normalize_journal_name(paper.journal_name)
        for entry in self.entries:
            if not entry.enabled:
                continue
            identifiers = entry.identifiers
            if paper_issns.intersection(identifiers):
                return WhitelistMatch(True, "issn", entry.name)
            if paper_issns and identifiers and not paper_issns.intersection(identifiers):
                continue
            if paper_name and paper_name == entry.normalized_name:
                return WhitelistMatch(True, "name", entry.name)
            if paper_name and paper_name in entry.normalized_aliases:
                return WhitelistMatch(True, "alias", entry.name)
        return WhitelistMatch(False)


def _find_header(headers: dict[str, str], *names: str) -> str | None:
    for name in names:
        if name.lower() in headers:
            return headers[name.lower()]
    return None


def _find_value(row: dict[str, str], headers: dict[str, str], *names: str) -> str | None:
    column = _find_header(headers, *names)
    return (row.get(column) or "").strip() if column else None
