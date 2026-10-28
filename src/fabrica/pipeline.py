"""Executor: roda as etapas de um vídeo respeitando dependências, em paralelo quando possível.

Cada etapa é idempotente do ponto de vista do pipeline: uma etapa 'done' não roda de novo,
então retomar um vídeo que falhou recomeça só do ponto da falha.
Só a thread principal escreve no banco; as etapas apenas leem e gravam arquivos.
"""
from __future__ import annotations

import logging
import traceback
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path

from fabrica.config import ChannelConfig, Settings, load_channels
from fabrica.db import Database, StageRun, StageStatus, Video, VideoStatus, utcnow
from fabrica.providers.image import make_image_gen
from fabrica.providers.llm import AnthropicLLM, FakeLLM
from fabrica.providers.notify import make_notifier
from fabrica.providers.renderer import FakeRenderer, make_renderer
from fabrica.providers.youtube import FakeUploader, YouTubeUploader
from fabrica.stages import ALL_STAGES, STAGE_NAMES
from fabrica.stages.base import Context, Providers, Stage, StageOutput

log = logging.getLogger("fabrica")
DONE = {StageStatus.done, StageStatus.skipped}


def build_providers(settings: Settings, channel: ChannelConfig, run_dir: Path, dry_run: bool) -> Providers:
    if dry_run:
        return Providers(llm=FakeLLM(), renderer=FakeRenderer(), image=make_image_gen("fake", ""),
                         uploader=FakeUploader(run_dir), notifier=make_notifier())
    t = channel.thumbnail
    return Providers(
        llm=AnthropicLLM(settings.llm_model),
        renderer=make_renderer(channel.video.engine),
        image=make_image_gen(t.provider, t.model) if t.enabled else None,
        uploader=YouTubeUploader(channel.resolve(channel.youtube.oauth_token)),
        notifier=make_notifier(),
    )


class Pipeline:
    def __init__(self, settings: Settings, db: Database | None = None, max_workers: int = 3):
        self.settings = settings
        self.db = db or Database(settings.database_url)
        self.max_workers = max_workers
        self.stages: dict[str, Stage] = {s.name: s for s in ALL_STAGES}

    def channels(self) -> dict[str, ChannelConfig]:
        return load_channels(self.settings.channels_dir)

    def create(self, channel_slug: str) -> Video:
        channels = self.channels()
        if channel_slug not in channels:
            raise KeyError(f"canal '{channel_slug}' não encontrado em {self.settings.channels_dir}")
        return self.db.new_video(channel_slug)

    def run(self, video_id: str, *, dry_run: bool | None = None, from_stage: str | None = None,
            until: str | None = None) -> Video:
        dry_run = self.settings.dry_run if dry_run is None else dry_run
        video = self.db.get(video_id)
        if video is None:
            raise KeyError(f"vídeo {video_id} não existe")
        channel = self.channels()[video.channel]
        run_dir = self.settings.runs_dir / video.channel / video.id
        run_dir.mkdir(parents=True, exist_ok=True)
        ctx = Context(self.settings, channel, video.id, run_dir,
                      build_providers(self.settings, channel, run_dir, dry_run),
                      recent_topics=self.db.recent_topics(channel.slug))

        if from_stage:  # refazer a partir de uma etapa: ela e as que dependem dela voltam a pending
            for name in self._downstream(from_stage):
                video.set_stage(name, StageStatus.pending)
        targets = set(self._upstream(until)) if until else set(STAGE_NAMES)

        video.status, video.error = VideoStatus.running, None
        self.db.save(video)
        ctx.providers.notifier.send(f"[{channel.slug}] vídeo {video.id} começou")

        failed = self._execute(video, ctx, targets)

        if failed:
            video.status = VideoStatus.failed
            ctx.providers.notifier.send(f"[{channel.slug}] {video.id} falhou na etapa {failed}: {video.error}")
        elif all(video.stage_status(n) in DONE for n in STAGE_NAMES):
            video.status = VideoStatus.scheduled
            ctx.providers.notifier.send(
                f"[{channel.slug}] agendado: {video.title} | youtu.be/{video.youtube_id} | {video.publish_at:%d/%m %H:%M} UTC")
        else:
            video.status = VideoStatus.queued  # parou antes do fim (--until)
        self.db.save(video)
        return video

    # ---------- execução ----------
    def _execute(self, video: Video, ctx: Context, targets: set[str]) -> str | None:
        running: dict[Future, str] = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as pool:
            while True:
                for name in self._ready(video, targets, running.values()):
                    stage = self.stages[name]
                    if not stage.enabled(ctx):
                        self._finish(video, name, StageOutput(detail="desativada no canal", skipped=True))
                        continue
                    video.set_stage(name, StageStatus.running)
                    self.db.save(video)
                    log.info("[%s] %s: iniciando %s", video.channel, video.id, name)
                    running[pool.submit(stage.run, ctx)] = name
                if not running:
                    return None
                done, _ = wait(running, return_when=FIRST_COMPLETED)
                for fut in done:
                    name = running.pop(fut)
                    try:
                        self._finish(video, name, fut.result())
                    except Exception as e:  # noqa: BLE001 - qualquer erro da etapa vira falha registrada
                        self._fail(video, name, e)
                        # espera as que já estão rodando terminarem antes de sair
                        for other in wait(running).done:
                            other_name = running[other]
                            try:
                                self._finish(video, other_name, other.result())
                            except Exception as e2:  # noqa: BLE001
                                self._fail(video, other_name, e2)
                        return name

    def _ready(self, video: Video, targets: set[str], running) -> list[str]:
        busy = set(running)
        out = []
        for name in STAGE_NAMES:
            if name not in targets or name in busy or video.stage_status(name) in DONE:
                continue
            if all(video.stage_status(d) in DONE for d in self.stages[name].depends_on):
                out.append(name)
        return out

    def _finish(self, video: Video, name: str, out: StageOutput) -> None:
        status = StageStatus.skipped if out.skipped else StageStatus.done
        video.set_stage(name, status)
        for k, v in out.video_updates.items():
            setattr(video, k, v)
        video.cost_usd = (video.cost_usd or 0.0) + out.cost_usd
        self.db.save(video)
        self.db.log_run(StageRun(video_id=video.id, stage=name, status=status, finished_at=utcnow(),
                                 detail=out.detail, cost_usd=out.cost_usd))
        log.info("[%s] %s: %s ok (%s)", video.channel, video.id, name, out.detail)

    def _fail(self, video: Video, name: str, err: Exception) -> None:
        video.set_stage(name, StageStatus.failed)
        video.error = f"{name}: {type(err).__name__}: {err}"
        self.db.save(video)
        self.db.log_run(StageRun(video_id=video.id, stage=name, status=StageStatus.failed, finished_at=utcnow(),
                                 detail="".join(traceback.format_exception(err))[-4000:]))
        log.error("[%s] %s: %s falhou: %s", video.channel, video.id, name, err)

    # ---------- grafo ----------
    def _downstream(self, name: str) -> list[str]:
        out, frontier = {name}, [name]
        while frontier:
            cur = frontier.pop()
            for s in ALL_STAGES:
                if cur in s.depends_on and s.name not in out:
                    out.add(s.name)
                    frontier.append(s.name)
        return [n for n in STAGE_NAMES if n in out]

    def _upstream(self, name: str) -> list[str]:
        out, frontier = {name}, [name]
        while frontier:
            for d in self.stages[frontier.pop()].depends_on:
                if d not in out:
                    out.add(d)
                    frontier.append(d)
        return [n for n in STAGE_NAMES if n in out]
