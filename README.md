# Fábrica de vídeos dark

Pipeline multi-canal que, para cada vídeo, escreve o roteiro, cria o vídeo com a skill
[lemo-opuscar](https://github.com/lemomo-ai/lemo-opuscar), gera título, descrição, tags e thumbnail por IA,
e agenda a publicação no YouTube para 30 minutos depois de o vídeo ficar pronto.

```
roteiro ──┬── vídeo (lemo-opuscar, 30–60 min) ───────────┐
          └── metadados ── thumbnail (brief, arte, texto, checagem) ─┴── upload agendado
```

## Como rodar

```sh
uv venv && uv pip install -e ".[youtube,api,dev]"
cp .env.example .env            # preencha ANTHROPIC_API_KEY, FAL_KEY etc.
fabrica channels                # lista e valida os canais
fabrica run exemplo-terror --dry-run   # tudo simulado, sem gastar nada
pytest
```

Comandos:

| Comando | O que faz |
|---|---|
| `fabrica channels` | Lista e valida `channels/<slug>/channel.yaml` |
| `fabrica new <slug>` | Cria um canal copiando o de exemplo |
| `fabrica run <slug> [--dry-run] [--until etapa]` | Cria um vídeo e roda o pipeline |
| `fabrica resume <id> [--from etapa]` | Retoma do ponto da falha, ou refaz a partir de uma etapa |
| `fabrica status [--channel slug]` | Últimos vídeos, etapas e custo |
| `fabrica auth-youtube <slug>` | Autoriza o upload num canal (uma vez) |
| `fabrica serve` | API HTTP para o n8n (`POST /runs`, `GET /runs/{id}`) |

## Estrutura

```
channels/<slug>/channel.yaml   um canal = um YAML (+ prompts/, selo, referências opcionais)
prompts/*.md                   prompts padrão; channels/<slug>/prompts/*.md sobrescreve
src/fabrica/
  config.py                    Settings (ambiente) e ChannelConfig (YAML)
  db.py                        estado: videos + stage_runs (SQLite ou Postgres)
  schemas.py                   formatos JSON de roteiro, metadados e thumbnail
  pipeline.py                  executor por dependências, em paralelo, retomável
  stages/                      script, render, metadata, thumbnail, upload
  providers/                   llm (Claude), renderer (Claude Code + lemo-opuscar), image (fal),
                               youtube, notify (Telegram) — cada um com versão simulada
  thumbnail_compose.py         texto, contorno, selo, 1280x720, até 2 MB
  cli.py, api.py
runs/<canal>/<video>/          tudo que um vídeo produz (script.json, video/, thumbs/, upload.json)
```

## Como escala

- Novo canal: só um YAML. O código é o mesmo para todos.
- Novo provedor (outro modelo de imagem, outra voz, outro uploader): uma classe em `providers/` com a mesma interface.
- Mais volume: troque `FABRICA_DATABASE_URL` para Postgres e rode mais workers (`fabrica serve` em várias máquinas).
- Etapas são retomáveis: uma falha no vídeo não refaz roteiro nem metadados.

## Segurança

- O vídeo roda `claude -p` com uma lista fechada de ferramentas (`--allowedTools`), sem modo de liberar tudo.
  Ajuste em `FABRICA_CLAUDE_ALLOWED_TOOLS`. Rode o worker numa máquina ou container dedicado.
- Tokens do YouTube ficam em `secrets/` (fora do git). Chaves só no `.env`.
- `fabrica serve` escuta em 127.0.0.1; defina `FABRICA_API_TOKEN` se expor para o n8n.

## Requisitos do worker de vídeo

Node 20+, ffmpeg, Python 3.11+, Claude Code e a skill:

```sh
claude plugin marketplace add lemomo-ai/lemo-opuscar
claude plugin install lemo-opuscar@lemolab
```

Para o texto das thumbnails, coloque uma fonte livre com acentos (por exemplo Anton, do Google Fonts) em
`fonts/` e aponte `thumbnail.text.font` para ela. Sem isso, usa DejaVu Sans Bold ou Arial do sistema.
