from sqlalchemy import select
from sqlalchemy.orm import Session

from models.db import DownloadedFile, DownloadTask
from models.domain import DownloadStatus
from repositories.database import create_database_engine
from repositories.downloads import DownloadRepository


def test_download_repository_persists_queue_state(tmp_path) -> None:
    engine = create_database_engine("sqlite:///:memory:")
    repository = DownloadRepository(engine)
    task_id = repository.create_task(
        1,
        source_url="https://repository.example/a.pdf",
        source="repository",
    )
    repository.update_task(
        task_id,
        status=DownloadStatus.DOWNLOADED,
        attempts=2,
        progress=1.0,
    )
    file_id = repository.add_file(
        task_id,
        tmp_path / "a.pdf",
        sha256="abc",
        size_bytes=10,
    )
    with Session(engine) as session:
        task = session.scalar(select(DownloadTask))
        downloaded = session.scalar(select(DownloadedFile))
        assert task is not None
        assert task.status == "DOWNLOADED"
        assert task.attempts == 2
        assert file_id == downloaded.id
