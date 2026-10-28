"""Configuração global (variáveis de ambiente) e por canal (um YAML por canal)."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, field_validator


class Settings(BaseModel):
    """Configuração da instalação, lida do ambiente (ou do .env)."""

    database_url: str = "sqlite:///data/fabrica.sqlite"
    runs_dir: Path = Path("runs")
    channels_dir: Path = Path("channels")
    prompts_dir: Path = Path("prompts")
    llm_model: str = "claude-opus-5-5"
    lemo_lib: Path = Path("~/lemo-opuscar").expanduser()
    dry_run: bool = False

    @classmethod
    def from_env(cls, root: Path | None = None) -> "Settings":
        root = root or Path.cwd()
        _load_dotenv(root / ".env")
        env = os.environ
        return cls(
            database_url=env.get("FABRICA_DATABASE_URL", f"sqlite:///{root / 'data' / 'fabrica.sqlite'}"),
            runs_dir=root / env.get("FABRICA_RUNS_DIR", "runs"),
            channels_dir=root / env.get("FABRICA_CHANNELS_DIR", "channels"),
            prompts_dir=root / env.get("FABRICA_PROMPTS_DIR", "prompts"),
            llm_model=env.get("FABRICA_LLM_MODEL", "claude-opus-5-5"),
            lemo_lib=Path(env.get("FABRICA_LEMO_LIB", "~/lemo-opuscar")).expanduser(),
            dry_run=env.get("FABRICA_DRY_RUN", "").lower() in ("1", "true", "yes"),
        )


def _load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip())


# ---------- configuração por canal ----------

class YouTubeConfig(BaseModel):
    channel_id: str = ""
    oauth_token: Path = Path("secrets/token.json")
    client_secrets: Path = Path("secrets/client_secret.json")
    category_id: str = "24"
    playlist_id: str | None = None
    made_for_kids: bool = False
    synthetic_media: bool = True
    default_language: str = "pt-BR"


class ScheduleConfig(BaseModel):
    cron: str = "0 14 * * *"
    publish_delay_min: int = Field(30, ge=0)
    timezone: str = "America/Sao_Paulo"


class ContentConfig(BaseModel):
    language: str = "pt-BR"
    niche: str
    tone: str = ""
    audience: str = ""
    avoid: list[str] = []
    format: Literal["short", "long"] = "short"
    duration_s: int = Field(50, gt=0)

    @property
    def size(self) -> tuple[int, int]:
        return (1080, 1920) if self.format == "short" else (1920, 1080)


class VoiceConfig(BaseModel):
    engine: Literal["edge-tts", "kokoro", "elevenlabs"] = "edge-tts"
    id: str = "pt-BR-AntonioNeural"
    speed: float = 0.95


class VideoConfig(BaseModel):
    engine: Literal["lemo-opuscar", "fake"] = "lemo-opuscar"
    style: str = "backrooms"
    voice: VoiceConfig = VoiceConfig()
    timeout_min: int = 90


class MetadataConfig(BaseModel):
    fixed_hashtags: list[str] = []
    fixed_tags: list[str] = []
    description_footer: str = ""


class ThumbnailTextConfig(BaseModel):
    max_words: int = Field(4, ge=1, le=8)
    font: Path | None = None
    color: str = "#F2E9C9"
    stroke: str = "#000000"


class ThumbnailConfig(BaseModel):
    enabled: bool = True
    provider: Literal["fal", "gemini", "openai", "fake"] = "fal"
    model: str = "fal-ai/flux-pro/v1.1"
    variants: int = Field(3, ge=1, le=5)
    style_prompt: str = ""
    use_video_ref: bool = True
    text: ThumbnailTextConfig = ThumbnailTextConfig()
    badge: Path | None = None
    keep_clear: Literal["bottom-right", "none"] = "bottom-right"
    min_score: float = Field(7.0, ge=0, le=10)


class ChannelConfig(BaseModel):
    slug: str
    name: str = ""
    enabled: bool = True
    youtube: YouTubeConfig = YouTubeConfig()
    schedule: ScheduleConfig = ScheduleConfig()
    content: ContentConfig
    video: VideoConfig = VideoConfig()
    metadata: MetadataConfig = MetadataConfig()
    thumbnail: ThumbnailConfig = ThumbnailConfig()
    # pasta do canal (onde o YAML mora); preenchida no load
    home: Path = Path(".")

    @field_validator("slug")
    @classmethod
    def _slug(cls, v: str) -> str:
        if not v.replace("-", "").isalnum() or v.lower() != v:
            raise ValueError("slug deve ter só letras minúsculas, números e hífens")
        return v

    def resolve(self, p: Path | None) -> Path | None:
        """Caminhos relativos no YAML são relativos à raiz do projeto."""
        if p is None:
            return None
        return p if p.is_absolute() else self.home.parent.parent / p


def load_channel(path: Path) -> ChannelConfig:
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    cfg = ChannelConfig.model_validate(data)
    cfg.home = path.parent
    return cfg


def load_channels(channels_dir: Path) -> dict[str, ChannelConfig]:
    """Cada canal vive em channels/<slug>/channel.yaml (pasta própria para refs, selo, prompts)."""
    found: dict[str, ChannelConfig] = {}
    for yml in sorted(channels_dir.glob("*/channel.yaml")):
        cfg = load_channel(yml)
        if cfg.slug != yml.parent.name:
            raise ValueError(f"{yml}: slug '{cfg.slug}' difere do nome da pasta '{yml.parent.name}'")
        found[cfg.slug] = cfg
    return found
