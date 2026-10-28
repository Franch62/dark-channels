"""Formatos dos arquivos que cada etapa grava na pasta do vídeo (e pede ao Claude em JSON)."""
from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class Scene(BaseModel):
    id: int
    narration: str = Field(description="Texto falado pelo narrador nesta cena")
    visual: str = Field(description="O que aparece na tela, em uma ou duas frases")
    duration_s: float = Field(description="Duração estimada da cena em segundos")


class Script(BaseModel):
    topic: str = Field(description="Tema em uma linha, usado para evitar repetição")
    angle: str = Field(description="O ângulo próprio deste vídeo, o que o diferencia")
    hook: str = Field(description="Primeira frase, para prender nos 3 primeiros segundos")
    scenes: list[Scene]
    outro: str = Field(description="Fechamento curto, com chamada para se inscrever se fizer sentido")
    total_duration_s: float

    @property
    def narration(self) -> str:
        return "\n\n".join([self.hook, *(s.narration for s in self.scenes), self.outro])


class Metadata(BaseModel):
    title: str = Field(description="Título, no máximo 100 caracteres")
    description: str = Field(description="Descrição do vídeo, sem as hashtags fixas do canal")
    tags: list[str] = Field(description="Tags de busca, sem o símbolo #")
    hashtags: list[str] = Field(description="Até 3 hashtags com #")
    thumbnail_text: str = Field(description="Texto de 2 a 4 palavras para a thumbnail, que complementa o título")

    @field_validator("title")
    @classmethod
    def _title(cls, v: str) -> str:
        v = " ".join(v.split())
        return v if len(v) <= 100 else v[:99].rstrip() + "…"

    def clamp_tags(self, extra: list[str], limit: int = 500) -> list[str]:
        """YouTube aceita no máximo 500 caracteres somando as tags (com vírgulas)."""
        out: list[str] = []
        total = 0
        for tag in [*extra, *self.tags]:
            tag = tag.strip().lstrip("#")
            if not tag or tag.lower() in (t.lower() for t in out):
                continue
            cost = len(tag) + (2 if " " in tag else 0) + (1 if out else 0)
            if total + cost > limit:
                break
            out.append(tag)
            total += cost
        return out


class ThumbConcept(BaseModel):
    prompt: str = Field(description="Prompt em inglês para o modelo de imagem, sem pedir texto na imagem")
    focal: str = Field(description="Elemento principal da imagem")
    emotion: str
    palette: str
    text: str = Field(description="Texto curto que vai sobre a imagem")


class ThumbBrief(BaseModel):
    concepts: list[ThumbConcept]


class ThumbScore(BaseModel):
    index: int
    legibility: float = Field(ge=0, le=10)
    title_match: float = Field(ge=0, le=10)
    safety_ok: bool = Field(description="Sem rosto real, marca, gore explícito ou conteúdo enganoso")
    score: float = Field(ge=0, le=10)
    notes: str


class ThumbCheck(BaseModel):
    scores: list[ThumbScore]
    best_index: int
