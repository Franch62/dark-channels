"""Etapa 1: roteiro em JSON, evitando temas já usados no canal."""
from __future__ import annotations

from fabrica.schemas import Script
from fabrica.stages.base import Context, Stage, StageOutput


class ScriptStage(Stage):
    name = "script"

    def run(self, ctx: Context) -> StageOutput:
        c = ctx.channel
        topics = "\n".join(f"- {t}" for t in ctx.recent_topics[:100]) or "(nenhum ainda)"
        prompt = ctx.prompt(
            "roteiro",
            channel_name=c.name or c.slug, niche=c.content.niche, tone=c.content.tone or "livre",
            audience=c.content.audience or "geral", language=c.content.language,
            format_label="Short vertical" if c.content.format == "short" else "vídeo longo horizontal",
            duration_s=c.content.duration_s, style=c.video.style,
            avoid="; ".join(c.content.avoid) or "nada específico", recent_topics=topics,
        )
        result = ctx.providers.llm.structured(prompt, Script, effort="high")
        script: Script = result.value
        if not script.scenes:
            raise ValueError("roteiro sem cenas")
        ctx.write_json("script.json", script)
        return StageOutput(detail=script.topic, cost_usd=result.cost_usd, video_updates={"topic": script.topic})
