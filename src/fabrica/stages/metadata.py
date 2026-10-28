"""Etapa 3: título, descrição, tags e o texto da thumbnail. Roda em paralelo ao vídeo."""
from __future__ import annotations

from fabrica.schemas import Metadata, Script
from fabrica.stages.base import Context, Stage, StageOutput


class MetadataStage(Stage):
    name = "metadata"
    depends_on = ("script",)

    def run(self, ctx: Context) -> StageOutput:
        c = ctx.channel
        script = ctx.read_json("script.json", Script)
        prompt = ctx.prompt(
            "metadados",
            channel_name=c.name or c.slug, niche=c.content.niche, language=c.content.language,
            fixed_hashtags=" ".join(c.metadata.fixed_hashtags) or "nenhuma",
            thumb_max_words=c.thumbnail.text.max_words, script_json=script.model_dump_json(indent=2),
        )
        result = ctx.providers.llm.structured(prompt, Metadata, effort="medium")
        meta: Metadata = result.value
        words = meta.thumbnail_text.split()
        if len(words) > c.thumbnail.text.max_words:
            meta.thumbnail_text = " ".join(words[: c.thumbnail.text.max_words])
        meta.tags = meta.clamp_tags(c.metadata.fixed_tags)
        ctx.write_json("meta.json", meta)
        return StageOutput(detail=meta.title, cost_usd=result.cost_usd, video_updates={"title": meta.title})


def full_description(meta: Metadata, ctx: Context) -> str:
    """Descrição final: texto do Claude + hashtags + rodapé fixo do canal (até 5000 caracteres)."""
    c = ctx.channel.metadata
    hashtags = " ".join(dict.fromkeys([*meta.hashtags, *c.fixed_hashtags]))
    parts = [meta.description.strip(), hashtags, c.description_footer.strip()]
    return "\n\n".join(p for p in parts if p)[:5000]
