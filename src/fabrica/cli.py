"""Linha de comando. Tudo que o n8n faz também pode ser feito à mão por aqui."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path

import typer

from fabrica.config import Settings, load_channels
from fabrica.pipeline import Pipeline
from fabrica.stages import STAGE_NAMES

app = typer.Typer(help="Fábrica de vídeos dark: roteiro, vídeo, metadados, thumbnail e upload agendado.",
                  no_args_is_help=True)


def _pipeline() -> Pipeline:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", datefmt="%H:%M:%S")
    return Pipeline(Settings.from_env())


@app.command()
def channels() -> None:
    """Lista e valida os canais em channels/<slug>/channel.yaml."""
    s = Settings.from_env()
    for slug, c in load_channels(s.channels_dir).items():
        state = "ativo" if c.enabled else "pausado"
        typer.echo(f"{slug:24} {state:8} {c.content.format:6} {c.video.style:18} {c.schedule.cron}  {c.content.niche}")


@app.command()
def new(slug: str, base: str = typer.Option("exemplo-terror", help="canal usado como modelo")) -> None:
    """Cria um canal novo copiando outro como modelo."""
    s = Settings.from_env()
    src, dst = s.channels_dir / base, s.channels_dir / slug
    if dst.exists():
        raise typer.BadParameter(f"{dst} já existe")
    shutil.copytree(src, dst)
    yml = dst / "channel.yaml"
    yml.write_text(yml.read_text(encoding="utf-8").replace(f"slug: {base}", f"slug: {slug}"), encoding="utf-8")
    typer.echo(f"criado {yml}. Edite nicho, estilo, voz e a conta do YouTube.")


@app.command()
def run(channel: str, dry_run: bool = typer.Option(False, "--dry-run", help="sem APIs: tudo simulado"),
        until: str = typer.Option(None, help=f"parar depois desta etapa ({', '.join(STAGE_NAMES)})")) -> None:
    """Cria um vídeo novo para o canal e roda o pipeline."""
    p = _pipeline()
    video = p.create(channel)
    typer.echo(f"vídeo {video.id}")
    video = p.run(video.id, dry_run=dry_run, until=until)
    _print(video)
    raise typer.Exit(1 if video.status.value == "failed" else 0)


@app.command()
def resume(video_id: str, dry_run: bool = typer.Option(False, "--dry-run"),
           from_stage: str = typer.Option(None, "--from", help="refazer a partir desta etapa")) -> None:
    """Retoma um vídeo do ponto em que parou (ou refaz a partir de uma etapa)."""
    p = _pipeline()
    video = p.run(video_id, dry_run=dry_run, from_stage=from_stage)
    _print(video)
    raise typer.Exit(1 if video.status.value == "failed" else 0)


@app.command()
def status(channel: str = typer.Option(None), limit: int = 20) -> None:
    """Últimos vídeos e o estado de cada etapa."""
    p = Pipeline(Settings.from_env())
    for v in p.db.list_videos(channel, limit):
        stages = " ".join(f"{n[:5]}:{v.stage_status(n).value[:4]}" for n in STAGE_NAMES)
        typer.echo(f"{v.id}  {v.channel:16} {v.status.value:9} US${v.cost_usd:6.2f}  {stages}  {v.title or ''}")


@app.command("auth-youtube")
def auth_youtube(channel: str) -> None:
    """Autoriza o upload num canal (abre o navegador, uma vez por canal)."""
    from fabrica.providers.youtube import authorize

    s = Settings.from_env()
    c = load_channels(s.channels_dir)[channel]
    authorize(c.resolve(c.youtube.client_secrets), c.resolve(c.youtube.oauth_token))
    typer.echo("token salvo")


@app.command()
def serve(host: str = "127.0.0.1", port: int = 8787) -> None:
    """API HTTP para o n8n disparar e acompanhar vídeos."""
    import uvicorn

    uvicorn.run("fabrica.api:app", host=host, port=port)


def _print(video) -> None:
    typer.echo(f"status: {video.status.value}  custo estimado: US${video.cost_usd:.2f}")
    for n in STAGE_NAMES:
        typer.echo(f"  {n:10} {video.stage_status(n).value}")
    if video.error:
        typer.echo(f"erro: {video.error}")
    if video.youtube_id:
        typer.echo(f"youtube: {video.youtube_id}  publica em {video.publish_at:%d/%m/%Y %H:%M} UTC")


if __name__ == "__main__":
    app()
