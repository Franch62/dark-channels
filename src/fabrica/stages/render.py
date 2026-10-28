"""Etapa 2: o vídeo, feito pela skill lemo-opuscar (ou pelo renderizador simulado)."""
from __future__ import annotations

from datetime import datetime, timezone

from fabrica.providers.renderer import RenderJob
from fabrica.schemas import Script
from fabrica.stages.base import Context, Stage, StageOutput


class RenderStage(Stage):
    name = "render"
    depends_on = ("script",)

    def run(self, ctx: Context) -> StageOutput:
        c = ctx.channel
        script = ctx.read_json("script.json", Script)
        width, height = c.content.size
        workdir = ctx.path("video")
        brief = ctx.prompt(
            "render_brief",
            style=c.video.style, language=c.content.language,
            voice_engine=c.video.voice.engine, voice_id=c.video.voice.id, voice_speed=c.video.voice.speed,
            width=width, height=height, duration_s=c.content.duration_s,
            workdir=workdir, script_json=script.model_dump_json(indent=2),
        )
        job = RenderJob(brief=brief, workdir=workdir, width=width, height=height,
                        duration_s=script.total_duration_s, timeout_min=c.video.timeout_min)
        result = ctx.providers.renderer.render(job)
        finished = datetime.now(timezone.utc)
        ctx.write_json("render.json", {
            "film": str(result.film), "subtitles": str(result.subtitles) if result.subtitles else None,
            "ref": str(result.ref) if result.ref else None, "finished_at": finished.isoformat(),
        })
        return StageOutput(detail=result.film.name, cost_usd=result.cost_usd)
