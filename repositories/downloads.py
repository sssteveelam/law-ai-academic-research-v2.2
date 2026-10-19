from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from models.db import DownloadedFile, DownloadTask, Paper
from models.domain import DownloadStatus


class DownloadRepository:
    """Persistence adapter for queue state; the queue remains usable in memory."""

    def __init__(self, engine: Any) -> None:
        self.engine = engine

    def create_task(
        self,
        paper_id: int,
        *,
        source_url: str | None,
        source: str | None,
    ) -> int:
        with Session(self.engine) as session:
            task = DownloadTask(
                paper_id=paper_id,
                status=DownloadStatus.DOWNLOAD_PENDING.value,
                source_url=source_url,
                source=source,
                created_at=datetime.utcnow(),
            )
            session.add(task)
            session.commit()
            return int(task.id)

    def update_task(
        self,
        task_id: int,
        *,
        status: DownloadStatus,
        attempts: int = 0,
        progress: float = 0.0,
        error_message: str | None = None,
    ) -> None:
        with Session(self.engine) as session:
            task = session.get(DownloadTask, task_id)
            if task is None:
                raise KeyError(f"unknown download task: {task_id}")
            task.status = status.value
            task.attempts = attempts
            task.progress = min(max(progress, 0.0), 1.0)
            task.error_message = error_message
            session.commit()

    def add_file(
        self,
        task_id: int,
        path: Path,
        *,
        sha256: str | None,
        size_bytes: int | None,
    ) -> int:
        with Session(self.engine) as session:
            item = DownloadedFile(
                task_id=task_id,
                local_path=str(path),
                sha256=sha256,
                size_bytes=size_bytes,
            )
            session.add(item)
            session.commit()
            return int(item.id)

    def list_history(self, limit: int = 100) -> list[dict[str, Any]]:
        """Return persisted task history even after Streamlit session expires."""
        with Session(self.engine) as session:
            rows = session.execute(
                select(DownloadTask, Paper.title, DownloadedFile.local_path)
                .join(Paper, Paper.id == DownloadTask.paper_id)
                .outerjoin(DownloadedFile, DownloadedFile.task_id == DownloadTask.id)
                .order_by(DownloadTask.created_at.desc(), DownloadTask.id.desc())
                .limit(limit)
            ).all()
            return [
                {
                    "id": task.id,
                    "paper_id": task.paper_id,
                    "title": title,
                    "status": task.status,
                    "source": task.source,
                    "attempts": task.attempts,
                    "error": task.error_message,
                    "file": path,
                    "created_at": task.created_at,
                }
                for task, title, path in rows
            ]

    def find_paper_id(self, paper: Any) -> int | None:
        with Session(self.engine) as session:
            if paper.doi:
                known = session.scalar(select(Paper.id).where(Paper.doi == paper.doi))
                if known is not None:
                    return int(known)
            known = session.scalar(
                select(Paper.id).where(
                    Paper.source_api == paper.source_api,
                    Paper.source_id == paper.source_id,
                )
            )
            return int(known) if known is not None else None
