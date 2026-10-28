"""Estado persistente: um registro por vídeo e um log por execução de etapa.

SQLite por padrão; para escalar (vários workers), aponte FABRICA_DATABASE_URL para Postgres.
"""
from __future__ import annotations

import enum
import uuid
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import JSON, DateTime, Enum, Float, ForeignKey, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class VideoStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    scheduled = "scheduled"   # enviado ao YouTube com publishAt
    published = "published"
    failed = "failed"
    canceled = "canceled"


class StageStatus(str, enum.Enum):
    pending = "pending"
    running = "running"
    done = "done"
    failed = "failed"
    skipped = "skipped"


class Base(DeclarativeBase):
    pass


class Video(Base):
    __tablename__ = "videos"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    channel: Mapped[str] = mapped_column(String(64), index=True)
    status: Mapped[VideoStatus] = mapped_column(Enum(VideoStatus), default=VideoStatus.queued, index=True)
    stages: Mapped[dict] = mapped_column(JSON, default=dict)        # nome da etapa -> StageStatus
    topic: Mapped[str | None] = mapped_column(Text)
    title: Mapped[str | None] = mapped_column(Text)
    youtube_id: Mapped[str | None] = mapped_column(String(32))
    publish_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    error: Mapped[str | None] = mapped_column(Text)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    runs: Mapped[list["StageRun"]] = relationship(back_populates="video", cascade="all, delete-orphan")

    def stage_status(self, name: str) -> StageStatus:
        return StageStatus(self.stages.get(name, StageStatus.pending.value))

    def set_stage(self, name: str, status: StageStatus) -> None:
        # reatribui o dict para o SQLAlchemy detectar a mudança no JSON
        self.stages = {**self.stages, name: status.value}


class StageRun(Base):
    __tablename__ = "stage_runs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    video_id: Mapped[str] = mapped_column(ForeignKey("videos.id"), index=True)
    stage: Mapped[str] = mapped_column(String(32))
    status: Mapped[StageStatus] = mapped_column(Enum(StageStatus))
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    detail: Mapped[str | None] = mapped_column(Text)
    cost_usd: Mapped[float] = mapped_column(Float, default=0.0)

    video: Mapped[Video] = relationship(back_populates="runs")


class Database:
    def __init__(self, url: str):
        if url.startswith("sqlite:///"):
            Path(url.removeprefix("sqlite:///")).parent.mkdir(parents=True, exist_ok=True)
        self.engine = create_engine(url, future=True)
        Base.metadata.create_all(self.engine)
        self._session = sessionmaker(self.engine, expire_on_commit=False)

    def session(self) -> Session:
        return self._session()

    def new_video(self, channel: str) -> Video:
        vid = f"{utcnow():%Y%m%d-%H%M}-{uuid.uuid4().hex[:6]}"
        video = Video(id=vid, channel=channel, stages={})
        with self.session() as s:
            s.add(video)
            s.commit()
        return video

    def get(self, video_id: str) -> Video | None:
        with self.session() as s:
            return s.get(Video, video_id)

    def save(self, video: Video) -> None:
        with self.session() as s:
            s.merge(video)
            s.commit()

    def log_run(self, run: StageRun) -> None:
        with self.session() as s:
            s.add(run)
            s.commit()

    def recent_topics(self, channel: str, limit: int = 200) -> list[str]:
        with self.session() as s:
            rows = s.scalars(
                select(Video.topic)
                .where(Video.channel == channel, Video.topic.is_not(None), Video.status != VideoStatus.canceled)
                .order_by(Video.created_at.desc())
                .limit(limit)
            )
            return [t for t in rows if t]

    def list_videos(self, channel: str | None = None, limit: int = 30) -> list[Video]:
        with self.session() as s:
            q = select(Video).order_by(Video.created_at.desc()).limit(limit)
            if channel:
                q = q.where(Video.channel == channel)
            return list(s.scalars(q))
