"""Etapa 4: thumbnail por IA. Brief (Claude) -> arte (modelo de imagem) -> texto (Pillow) -> checagem (Claude com visão)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

from fabrica.schemas import Metadata, Script, ThumbBrief, ThumbCheck
from fabrica.stages.base import Context, Stage, StageOutput
from fabrica.thumbnail_compose import THUMB_SIZE, compose

log = logging.getLogger("fabrica")


class ThumbnailStage(Stage):
    name = "thumbnail"
    depends_on = ("script", "metadata")

    def enabled(self, ctx: Context) -> bool:
        return ctx.channel.thumbnail.enabled

    def run(self, ctx: Context) -> StageOutput:
        c, t = ctx.channel, ctx.channel.thumbnail
        script = ctx.read_json("script.json", Script)
        meta = ctx.read_json("meta.json", Metadata)
        cost = 0.0

        # 4a. brief
        brief_prompt = ctx.prompt(
            "thumb_brief",
            channel_name=c.name or c.slug, niche=c.content.niche, title=meta.title,
            thumbnail_text=meta.thumbnail_text, style_prompt=t.style_prompt or c.video.style,
            text_zone="no terço inferior esquerdo" if t.keep_clear == "bottom-right" else "no centro",
            variants=t.variants, thumb_max_words=t.text.max_words,
            summary=f"{script.hook} {script.angle}",
        )
        r = ctx.providers.llm.structured(brief_prompt, ThumbBrief, effort="medium")
        brief: ThumbBrief = r.value
        cost += r.cost_usd
        ctx.write_json("thumbs/brief.json", brief)

        # 4b + 4c. arte e composição, uma por conceito
        ref = self._ref(ctx) if t.use_video_ref else None
        if ctx.providers.image is None:
            raise RuntimeError("nenhum provedor de imagem configurado")
        candidates: list[Path] = []
        for i, concept in enumerate(brief.concepts[: t.variants]):
            prompt = f"{concept.prompt}. {t.style_prompt}".strip(". ")
            art = ctx.providers.image.generate(prompt, *THUMB_SIZE, ref=ref)
            art_path = ctx.path(f"thumbs/art_{i}.png")
            art_path.write_bytes(art)
            text = " ".join((concept.text or meta.thumbnail_text).split()[: t.text.max_words])
            out = compose(art_path, text, ctx.path(f"thumbs/thumb_{i}.jpg"),
                          font_path=c.resolve(t.text.font), color=t.text.color, stroke=t.text.stroke,
                          badge=c.resolve(t.badge), keep_clear=t.keep_clear)
            candidates.append(out)

        # 4d. checagem com visão
        check_prompt = ctx.prompt("thumb_check", channel_name=c.name or c.slug, title=meta.title,
                                  count=len(candidates))
        r = ctx.providers.llm.structured(check_prompt, ThumbCheck, images=candidates, effort="medium")
        check: ThumbCheck = r.value
        cost += r.cost_usd
        ctx.write_json("thumbs/check.json", check)

        safe = {s.index: s for s in check.scores if s.safety_ok and 0 <= s.index < len(candidates)}
        best = check.best_index if check.best_index in safe else max(safe, key=lambda i: safe[i].score, default=None)
        if best is None:
            raise RuntimeError("nenhuma thumbnail passou na checagem de segurança")
        if safe[best].score < t.min_score:
            log.warning("melhor thumbnail com nota %.1f, abaixo do mínimo %.1f", safe[best].score, t.min_score)
        chosen = ctx.path("thumbs/thumb.jpg")
        chosen.write_bytes(candidates[best].read_bytes())
        return StageOutput(detail=f"versão {best}, nota {safe[best].score:.1f}", cost_usd=cost)

    @staticmethod
    def _ref(ctx: Context) -> Path | None:
        """Quadro de referência do vídeo, se a etapa de vídeo já tiver gravado (roda em paralelo)."""
        ref = ctx.path("video/ref.jpg")
        if ref.exists():
            return ref
        rj = ctx.path("render.json")
        if rj.exists():
            p = json.loads(rj.read_text()).get("ref")
            if p and Path(p).exists():
                return Path(p)
        return None
