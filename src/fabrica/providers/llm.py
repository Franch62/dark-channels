"""Chamadas de texto ao Claude com saída validada por um modelo Pydantic."""
from __future__ import annotations

import base64
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol, TypeVar

from pydantic import BaseModel

T = TypeVar("T", bound=BaseModel)

# preço por milhão de tokens (entrada, saída), para estimar custo no log
PRICES = {
    "claude-opus-5-5": (4.0, 20.0),
    "claude-sonnet-5-5": (2.0, 10.0),
    "claude-haiku-5-5": (0.10, 0.50),
}


@dataclass
class LLMResult:
    value: Any
    cost_usd: float = 0.0


class LLM(Protocol):
    def structured(self, prompt: str, schema: type[T], images: list[Path] | None = None,
                   effort: str = "medium") -> LLMResult: ...


class LLMRefusal(RuntimeError):
    pass


def image_block(path: Path) -> dict:
    media = "image/png" if path.suffix.lower() == ".png" else "image/jpeg"
    data = base64.standard_b64encode(path.read_bytes()).decode("ascii")
    return {"type": "image", "source": {"type": "base64", "media_type": media, "data": data}}


class AnthropicLLM:
    def __init__(self, model: str = "claude-opus-5-5"):
        import anthropic

        self.client = anthropic.Anthropic()
        self.model = model

    def structured(self, prompt: str, schema: type[T], images: list[Path] | None = None,
                   effort: str = "medium") -> LLMResult:
        content: list[dict] = [image_block(p) for p in images or []]
        content.append({"type": "text", "text": prompt})
        # fallbacks "default": se um classificador recusar (comum em temas de terror),
        # a API reexecuta no modelo indicado para aquela categoria, na mesma chamada
        response = self.client.beta.messages.parse(
            model=self.model,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            output_config={"effort": effort},
            messages=[{"role": "user", "content": content}],
            output_format=schema,
        )
        if response.stop_reason == "refusal":
            raise LLMRefusal(f"o modelo recusou o pedido: {response.stop_details}")
        if response.stop_reason == "max_tokens":
            raise RuntimeError("resposta cortada por max_tokens")
        return LLMResult(response.parsed_output, self._cost(response.usage))

    def _cost(self, usage: Any) -> float:
        price_in, price_out = PRICES.get(self.model, (0.0, 0.0))
        return (usage.input_tokens * price_in + usage.output_tokens * price_out) / 1_000_000


class FakeLLM:
    """Respostas fixas para testes e execuções simuladas (--dry-run), sem custo."""

    def structured(self, prompt: str, schema: type[T], images: list[Path] | None = None,
                   effort: str = "medium") -> LLMResult:
        from fabrica import schemas as s

        if schema is s.Script:
            value = s.Script(
                topic="O andar 7 que não aparece no elevador",
                angle="Contado como o relatório interno de um zelador noturno",
                hook="O elevador deste prédio tem botões do 1 ao 12. Mas ele já parou no 7.",
                scenes=[
                    s.Scene(id=1, narration="Na terceira noite, a porta abriu num corredor que não existia.",
                            visual="Corredor longo com luz fluorescente piscando", duration_s=12),
                    s.Scene(id=2, narration="Havia um aviso: não conte as portas. Ele contou.",
                            visual="Folha impressa colada na parede", duration_s=14),
                    s.Scene(id=3, narration="Eram quarenta e uma. Na volta, quarenta e duas.",
                            visual="Câmera passando por portas iguais", duration_s=14),
                ],
                outro="Se o seu prédio tem um andar que falta, conte nos comentários.",
                total_duration_s=48,
            )
        elif schema is s.Metadata:
            value = s.Metadata(
                title="O elevador parou num andar que não existe",
                description="Um zelador noturno registrou o que viu no andar 7.\n\nOuça até o fim.",
                tags=["andar 7", "relato de terror", "liminal", "creepypasta", "terror"],
                hashtags=["#liminal"],
                thumbnail_text="NÃO CONTE AS PORTAS",
            )
        elif schema is s.ThumbBrief:
            value = s.ThumbBrief(concepts=[
                s.ThumbConcept(prompt=f"empty fluorescent corridor, concept {i}", focal="porta entreaberta",
                               emotion="inquietação", palette="verde e amarelo doentio",
                               text="NÃO CONTE AS PORTAS")
                for i in range(3)
            ])
        elif schema is s.ThumbCheck:
            n = len(images or []) or 1
            value = s.ThumbCheck(
                scores=[s.ThumbScore(index=i, legibility=8, title_match=8, safety_ok=True,
                                     score=8 - i * 0.5, notes="simulado") for i in range(n)],
                best_index=0,
            )
        else:
            raise NotImplementedError(f"FakeLLM não conhece {schema.__name__}")
        return LLMResult(value, 0.0)
