from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.db import JournalRanking, TargetJournal
from services.ranking.identifiers import normalize_issn
from models.domain import Quartile
from services.ranking.scimago import ScimagoRow, ScimagoCSVImporter
from services.ranking.whitelist import JournalWhitelist, JournalWhitelistEntry


class RankingRepository:
    def __init__(self, engine: Any) -> None:
        self.engine = engine

    def replace_source_rows(self, rows: list[ScimagoRow]) -> int:
        """Replace only imported rows for one ranking source."""
        with Session(self.engine) as session:
            source = rows[0].source if rows else "SCImago SJR"
            session.query(JournalRanking).filter(JournalRanking.source == source).delete(
                synchronize_session=False
            )
            # Collapse duplicate CSV identifiers and mark inconsistent quartiles
            # as Unknown instead of failing an entire SJR import transaction.
            pending: dict[tuple, JournalRanking] = {}
            for row in rows:
                identifiers = sorted(set(row.issns) | ({row.issn_l} if row.issn_l else set()))
                for issn in identifiers or [None]:
                    identity = issn or f"journal:{row.journal_name.casefold()}"
                    key = (identity, row.ranking_year, row.subject, row.source)
                    if key not in pending:
                        pending[key] = JournalRanking(
                            issn=issn,
                            journal_name=row.journal_name,
                            quartile=row.quartile.value,
                            ranking_year=row.ranking_year,
                            subject=row.subject,
                            source=row.source,
                        )
                    elif pending[key].quartile != row.quartile.value:
                        pending[key].quartile = Quartile.UNKNOWN.value
            session.add_all(pending.values())
            session.commit()
            return len(rows)

    def upsert_whitelist(self, entries: list[JournalWhitelistEntry]) -> int:
        with Session(self.engine) as session:
            for entry in entries:
                existing = session.scalar(
                    select(TargetJournal).where(
                        TargetJournal.normalized_name == entry.normalized_name
                    )
                )
                if existing is None:
                    existing = TargetJournal(
                        name=entry.name,
                        normalized_name=entry.normalized_name,
                    )
                    session.add(existing)
                existing.name = entry.name
                existing.group_name = entry.group
                existing.issns = sorted(
                    value
                    for value in (normalize_issn(item) for item in entry.issns)
                    if value
                )
                existing.issn_l = normalize_issn(entry.issn_l)
                existing.aliases = sorted(entry.aliases)
                existing.enabled = entry.enabled
                existing.source = entry.source
                existing.updated_at = entry.updated_at or datetime.utcnow()
            session.commit()
            return len(entries)

    def list_whitelist(self) -> list[TargetJournal]:
        with Session(self.engine) as session:
            return list(
                session.scalars(
                    select(TargetJournal).order_by(TargetJournal.normalized_name)
                ).all()
            )


    def load_rankings(self) -> ScimagoCSVImporter:
        """Rebuild the SJR index from persisted data for later search sessions."""
        with Session(self.engine) as session:
            stored = session.scalars(select(JournalRanking).order_by(JournalRanking.id)).all()
            grouped: dict[tuple, set[str]] = {}
            for row in stored:
                key = (row.journal_name, row.quartile, row.ranking_year, row.subject, row.source)
                grouped.setdefault(key, set())
                if row.issn:
                    normalized = normalize_issn(row.issn)
                    if normalized:
                        grouped[key].add(normalized)
            return ScimagoCSVImporter([
                ScimagoRow(
                    journal_name=name,
                    issns=tuple(sorted(issns)),
                    issn_l=None,
                    quartile=Quartile(quartile) if quartile in Quartile._value2member_map_ else Quartile.UNKNOWN,
                    ranking_year=year,
                    subject=subject,
                    source=source,
                )
                for (name, quartile, year, subject, source), issns in grouped.items()
            ])

    def load_whitelist(self) -> JournalWhitelist:
        """Database entries, including disabled status, are the effective whitelist."""
        return JournalWhitelist([
            JournalWhitelistEntry(
                name=item.name,
                group=item.group_name,
                issns=set(item.issns or []),
                issn_l=item.issn_l,
                aliases=set(item.aliases or []),
                enabled=item.enabled,
                source=item.source,
                updated_at=item.updated_at,
            )
            for item in self.list_whitelist()
        ])

    def ranking_count(self) -> int:
        with Session(self.engine) as session:
            return session.query(JournalRanking).count()

    def remove_whitelist(self, normalized_name: str) -> bool:
        with Session(self.engine) as session:
            entry = session.scalar(
                select(TargetJournal).where(
                    TargetJournal.normalized_name == normalized_name
                )
            )
            if entry is None:
                return False
            session.delete(entry)
            session.commit()
            return True
