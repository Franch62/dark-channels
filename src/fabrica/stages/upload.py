"""Etapa 5: upload privado com publishAt = fim do vídeo + atraso do canal (30 min por padrão)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path

from fabrica.providers.youtube import UploadRequest
from fabrica.schemas import Metadata
from fabrica.stages.base import Context, Stage, StageOutput
from fabrica.stages.metadata import full_description

# o YouTube exige publishAt no futuro; se o upload atrasar, empurra para pelo menos isto
MIN_LEAD = timedelta(minutes=10)


def publish_time(render_finished: datetime, delay_min: int, now: datetime | None = None) -> datetime:
    now = now or datetime.now(timezone.utc)
    return max(render_finished + timedelta(minutes=delay_min), now + MIN_LEAD)


class UploadStage(Stage):
    name = "upload"
    depends_on = ("render", "metadata", "thumbnail")

    def run(self, ctx: Context) -> StageOutput:
        c = ctx.channel
        meta = ctx.read_json("meta.json", Metadata)
        render = ctx.read_json("render.json")
        finished = datetime.fromisoformat(render["finished_at"])
        publish_at = publish_time(finished, c.schedule.publish_delay_min)
        thumb = ctx.path("thumbs/thumb.jpg")
        req = UploadRequest(
            file=Path(render["film"]), title=meta.title, description=full_description(meta, ctx),
            tags=meta.tags, category_id=c.youtube.category_id, publish_at=publish_at,
            language=c.youtube.default_language, made_for_kids=c.youtube.made_for_kids,
            synthetic_media=c.youtube.synthetic_media, thumbnail=thumb if thumb.exists() else None,
            playlist_id=c.youtube.playlist_id,
            subtitles=Path(render["subtitles"]) if render.get("subtitles") else None,
        )
        result = ctx.providers.uploader.upload(req)
        ctx.write_json("upload.json", {"video_id": result.video_id, "publish_at": publish_at.isoformat(),
                                       "thumbnail_ok": result.thumbnail_ok, "warnings": result.warnings})
        detail = f"youtu.be/{result.video_id} às {publish_at:%H:%M} UTC"
        if result.warnings:
            detail += " (avisos: " + "; ".join(result.warnings) + ")"
        return StageOutput(detail=detail, video_updates={"youtube_id": result.video_id, "publish_at": publish_at})
