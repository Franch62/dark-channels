"""API mínima para o n8n: dispara um vídeo e consulta o estado.

POST /runs {"channel": "exemplo-terror", "dry_run": false}  -> {"video_id": ...}
GET  /runs/{video_id}                                      -> estado e etapas
POST /runs/{video_id}/resume                               -> retoma do ponto da falha
GET  /channels                                             -> canais configurados

Escute só em 127.0.0.1 ou atrás de um proxy com autenticação; defina FABRICA_API_TOKEN para exigir
o cabeçalho Authorization: Bearer <token>.
"""
from __future__ import annotations

import os
import threading

from fastapi import Depends, FastAPI, Header, HTTPException
from pydantic import BaseModel

from fabrica.config import Settings
from fabrica.pipeline import Pipeline
from fabrica.stages import STAGE_NAMES

app = FastAPI(title="fabrica")
_pipeline = Pipeline(Settings.from_env())
_lock = threading.Lock()  # um vídeo por vez por worker; escale com mais workers


def _auth(authorization: str | None = Header(default=None)) -> None:
    token = os.environ.get("FABRICA_API_TOKEN")
    if token and authorization != f"Bearer {token}":
        raise HTTPException(401, "token inválido")


class RunRequest(BaseModel):
    channel: str
    dry_run: bool = False


def _view(video) -> dict:
    return {
        "video_id": video.id, "channel": video.channel, "status": video.status.value,
        "stages": {n: video.stage_status(n).value for n in STAGE_NAMES},
        "title": video.title, "youtube_id": video.youtube_id,
        "publish_at": video.publish_at.isoformat() if video.publish_at else None,
        "error": video.error, "cost_usd": round(video.cost_usd or 0, 4),
    }


def _work(video_id: str, **kw) -> None:
    with _lock:
        _pipeline.run(video_id, **kw)


@app.get("/channels", dependencies=[Depends(_auth)])
def channels() -> list[dict]:
    return [{"slug": c.slug, "enabled": c.enabled, "cron": c.schedule.cron, "format": c.content.format}
            for c in _pipeline.channels().values()]


@app.post("/runs", dependencies=[Depends(_auth)])
def start(req: RunRequest) -> dict:
    try:
        video = _pipeline.create(req.channel)
    except KeyError as e:
        raise HTTPException(404, str(e)) from e
    threading.Thread(target=_work, args=(video.id,), kwargs={"dry_run": req.dry_run}, daemon=True).start()
    return _view(video)


@app.get("/runs/{video_id}", dependencies=[Depends(_auth)])
def get(video_id: str) -> dict:
    video = _pipeline.db.get(video_id)
    if video is None:
        raise HTTPException(404, "vídeo não encontrado")
    return _view(video)


@app.post("/runs/{video_id}/resume", dependencies=[Depends(_auth)])
def resume(video_id: str, dry_run: bool = False) -> dict:
    video = _pipeline.db.get(video_id)
    if video is None:
        raise HTTPException(404, "vídeo não encontrado")
    threading.Thread(target=_work, args=(video_id,), kwargs={"dry_run": dry_run}, daemon=True).start()
    return _view(video)
