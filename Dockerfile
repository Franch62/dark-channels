# Worker: pipeline + Claude Code + dependências da lemo-opuscar (Node, ffmpeg, Chromium).
FROM node:22-bookworm
RUN apt-get update && apt-get install -y --no-install-recommends \
      python3 python3-venv ffmpeg fonts-dejavu-core chromium \
    && rm -rf /var/lib/apt/lists/*
RUN npm install -g @anthropic-ai/claude-code
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
RUN python3 -m venv /venv && /venv/bin/pip install --no-cache-dir -e ".[youtube,api]"
COPY prompts ./prompts
ENV PATH="/venv/bin:$PATH"
# a skill é instalada no primeiro start (precisa de rede e da chave)
CMD ["sh", "-c", "claude plugin marketplace add lemomo-ai/lemo-opuscar >/dev/null 2>&1; claude plugin install lemo-opuscar@lemolab >/dev/null 2>&1; fabrica serve --host 0.0.0.0"]
