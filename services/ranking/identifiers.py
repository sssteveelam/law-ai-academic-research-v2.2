from __future__ import annotations

import re
import unicodedata


def normalize_issn(value: str | None) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"[^0-9Xx]", "", str(value)).upper()
    return cleaned if len(cleaned) == 8 else None


def split_issns(value: str | None) -> list[str]:
    if not value:
        return []
    values = re.split(r"[,;|/\s]+", value)
    result: list[str] = []
    for item in values:
        normalized = normalize_issn(item)
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def normalize_journal_name(value: str | None) -> str:
    if not value:
        return ""
    decomposed = unicodedata.normalize("NFKD", value)
    without_marks = "".join(
        char for char in decomposed if not unicodedata.combining(char)
    )
    return re.sub(r"[^a-z0-9]+", " ", without_marks.lower()).strip()
