"""Criação do vídeo. Produção: Claude Code headless com a skill lemo-opuscar."""
from __future__ import annotations

import json
import os
import shlex
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

# Ferramentas que o agente pode usar sem pedir aprovação. Só o necessário para a skill:
# ler/escrever arquivos na pasta do vídeo e rodar node, python, sh e ffmpeg.
# Ajuste por máquina com FABRICA_CLAUDE_ALLOWED_TOOLS; não há modo "liberar tudo" por padrão.
DEFAULT_ALLOWED_TOOLS = [
    "Read", "Write", "Edit", "Glob", "Grep",
    "Bash(node:*)", "Bash(npm:*)", "Bash(npx:*)", "Bash(sh:*)", "Bash(python3:*)",
    "Bash(ffmpeg:*)", "Bash(ffprobe:*)", "Bash(ls:*)", "Bash(mkdir:*)", "Bash(cp:*)", "Bash(cd:*)",
]


@dataclass
class RenderJob:
    brief: str           # prompt completo para o agente
    workdir: Path        # pasta onde film.mp4, film.srt e ref.jpg devem aparecer
    width: int
    height: int
    duration_s: float
    timeout_min: int


@dataclass
class RenderResult:
    film: Path
    subtitles: Path | None
    ref: Path | None
    cost_usd: float = 0.0


class Renderer(Protocol):
    def render(self, job: RenderJob) -> RenderResult: ...


def _collect(workdir: Path) -> RenderResult:
    film = workdir / "film.mp4"
    if not film.exists():
        # a skill às vezes cria uma subpasta de projeto; aceita o mp4 final mais recente
        mp4s = sorted(workdir.rglob("*.mp4"), key=lambda p: p.stat().st_mtime, reverse=True)
        mp4s = [p for p in mp4s if "/out/" not in p.as_posix()] or mp4s
        if not mp4s:
            raise RuntimeError(f"nenhum film.mp4 em {workdir}")
        shutil.copy2(mp4s[0], film)
    srt = workdir / "film.srt"
    if not srt.exists():
        found = sorted(workdir.rglob("*.srt"))
        if found:
            shutil.copy2(found[0], srt)
    ref = workdir / "ref.jpg"
    return RenderResult(film=film, subtitles=srt if srt.exists() else None, ref=ref if ref.exists() else None)


class LemoOpuscarRenderer:
    """Roda `claude -p` dentro da pasta do vídeo, com a skill lemo-opuscar instalada na máquina:

        claude plugin marketplace add lemomo-ai/lemo-opuscar
        claude plugin install lemo-opuscar@lemolab
    """

    def __init__(self, claude_bin: str = "claude"):
        self.claude_bin = claude_bin
        allowed = os.environ.get("FABRICA_CLAUDE_ALLOWED_TOOLS")
        self.allowed_tools = allowed.split(",") if allowed else DEFAULT_ALLOWED_TOOLS
        self.extra_args = shlex.split(os.environ.get("FABRICA_CLAUDE_ARGS", ""))

    def command(self, job: RenderJob) -> list[str]:
        return [self.claude_bin, "-p", job.brief, "--output-format", "json",
                "--allowedTools", ",".join(self.allowed_tools), *self.extra_args]

    def render(self, job: RenderJob) -> RenderResult:
        if shutil.which(self.claude_bin) is None:
            raise RuntimeError("Claude Code (comando 'claude') não encontrado no PATH do worker")
        job.workdir.mkdir(parents=True, exist_ok=True)
        (job.workdir / "BRIEF.md").write_text(job.brief, encoding="utf-8")
        proc = subprocess.run(self.command(job), cwd=job.workdir, capture_output=True, text=True,
                              timeout=job.timeout_min * 60)
        (job.workdir / "agent.log").write_text(proc.stdout + "\n--- stderr ---\n" + proc.stderr, encoding="utf-8")
        if proc.returncode != 0:
            raise RuntimeError(f"claude saiu com código {proc.returncode}: {proc.stderr[-800:]}")
        result = _collect(job.workdir)
        result.cost_usd = _cost_from_json(proc.stdout)
        return result


def _cost_from_json(stdout: str) -> float:
    try:
        return float(json.loads(stdout).get("total_cost_usd", 0.0))
    except (ValueError, AttributeError):
        return 0.0


class FakeRenderer:
    """Vídeo curto de teste com ffmpeg (tela colorida + tom), para --dry-run e testes."""

    def render(self, job: RenderJob) -> RenderResult:
        job.workdir.mkdir(parents=True, exist_ok=True)
        (job.workdir / "BRIEF.md").write_text(job.brief, encoding="utf-8")
        film = job.workdir / "film.mp4"
        dur = min(3.0, job.duration_s)
        w, h = (job.width // 4) * 2, (job.height // 4) * 2  # metade do tamanho, para ser rápido
        subprocess.run(
            ["ffmpeg", "-y", "-loglevel", "error",
             "-f", "lavfi", "-i", f"color=c=0x1d2b24:s={w}x{h}:d={dur}",
             "-f", "lavfi", "-i", f"sine=frequency=110:duration={dur}",
             "-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", str(film)],
            check=True,
        )
        (job.workdir / "film.srt").write_text("1\n00:00:00,000 --> 00:00:03,000\n(simulado)\n", encoding="utf-8")
        from PIL import Image

        Image.new("RGB", (1280, 720), (40, 60, 45)).save(job.workdir / "ref.jpg", quality=90)
        return _collect(job.workdir)


def make_renderer(engine: str) -> Renderer:
    return FakeRenderer() if engine == "fake" else LemoOpuscarRenderer()
