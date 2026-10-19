from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ResearchProfile:
    name: str
    primary_keywords: tuple[str, ...]
    extended_keywords: tuple[str, ...]
    excluded_keywords: tuple[str, ...]
    target_journals: tuple[dict[str, str], ...]

    @classmethod
    def from_file(cls, path: Path) -> ResearchProfile:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return cls(
            name=raw["name"],
            primary_keywords=tuple(raw.get("primary_keywords", [])),
            extended_keywords=tuple(raw.get("extended_keywords", [])),
            excluded_keywords=tuple(raw.get("excluded_keywords", [])),
            target_journals=tuple(raw.get("target_journals", [])),
        )

    def build_query(self, *, include_extended: bool = True) -> str:
        terms = list(self.primary_keywords)
        if include_extended:
            terms.extend(self.extended_keywords)
        terms = [term.strip() for term in terms if term.strip()]
        return " OR ".join(f'"{term}"' if " " in term else term for term in terms)
