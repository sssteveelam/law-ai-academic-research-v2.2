from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.db import KeywordPreset


class SettingsRepository:
    def __init__(self, engine: Any) -> None:
        self.engine = engine

    def save_keyword_preset(self, name: str, keywords: dict[str, list[str]]) -> int:
        with Session(self.engine) as session:
            preset = session.scalar(
                select(KeywordPreset).where(KeywordPreset.name == name)
            )
            if preset is None:
                preset = KeywordPreset(name=name)
                session.add(preset)
            preset.keywords = keywords
            session.commit()
            return int(preset.id)

    def list_keyword_presets(self) -> list[KeywordPreset]:
        with Session(self.engine) as session:
            return list(
                session.scalars(select(KeywordPreset).order_by(KeywordPreset.name)).all()
            )
