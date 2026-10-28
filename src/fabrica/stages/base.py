"""Contrato de uma etapa e o contexto que ela recebe."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, ClassVar

from pydantic import BaseModel

from fabrica.config import ChannelConfig, Settings
from fabrica.providers.image import ImageGen
from fabrica.providers.llm import LLM
from fabrica.providers.notify import Notifier
from fabrica.providers.renderer import Renderer
from fabrica.providers.youtube import Uploader


@dataclass
class Providers:
    llm: LLM
    renderer: Renderer
    image: ImageGen | None
    uploader: Uploader
    notifier: Notifier


@dataclass
class Context:
    settings: Settings
    channel: ChannelConfig
    video_id: str
    run_dir: Path
    providers: Providers
    recent_topics: list[str] = field(default_factory=list)

    # ---------- arquivos da pasta do vídeo ----------
    def path(self, name: str) -> Path:
        return self.run_dir / name

    def write_json(self, name: str, data: BaseModel | dict) -> Path:
        p = self.path(name)
        p.parent.mkdir(parents=True, exist_ok=True)
        text = data.model_dump_json(indent=2) if isinstance(data, BaseModel) else json.dumps(
            data, ensure_ascii=False, indent=2, default=str)
        p.write_text(text, encoding="utf-8")
        return p

    def read_json(self, name: str, model: type[BaseModel] | None = None) -> Any:
        raw = self.path(name).read_text(encoding="utf-8")
        return model.model_validate_json(raw) if model else json.loads(raw)

    # ---------- prompts ----------
    def prompt(self, name: str, **values: Any) -> str:
        """Usa channels/<slug>/prompts/<name>.md se existir, senão prompts/<name>.md."""
        override = self.channel.home / "prompts" / f"{name}.md"
        path = override if override.exists() else self.settings.prompts_dir / f"{name}.md"
        return path.read_text(encoding="utf-8").format_map(_Missing(values))


class _Missing(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


@dataclass
class StageOutput:
    detail: str = ""
    cost_usd: float = 0.0
    video_updates: dict[str, Any] = field(default_factory=dict)  # campos do registro Video
    skipped: bool = False


class Stage:
    name: ClassVar[str]
    depends_on: ClassVar[tuple[str, ...]] = ()

    def enabled(self, ctx: Context) -> bool:
        return True

    def run(self, ctx: Context) -> StageOutput:
        raise NotImplementedError
