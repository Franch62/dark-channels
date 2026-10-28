"""Geração da arte da thumbnail (sem texto) por um modelo de imagem."""
from __future__ import annotations

import base64
import os
from pathlib import Path
from typing import Protocol

import httpx


class ImageGen(Protocol):
    def generate(self, prompt: str, width: int, height: int, ref: Path | None = None) -> bytes: ...


class FalImage:
    """Modelos Flux e outros via fal.ai (endpoint síncrono fal.run). Precisa de FAL_KEY."""

    def __init__(self, model: str):
        key = os.environ.get("FAL_KEY")
        if not key:
            raise RuntimeError("FAL_KEY não definido")
        self.model = model
        self.http = httpx.Client(timeout=180, headers={"Authorization": f"Key {key}"})

    def generate(self, prompt: str, width: int, height: int, ref: Path | None = None) -> bytes:
        body: dict = {"prompt": prompt, "image_size": {"width": width, "height": height}, "num_images": 1}
        if ref is not None and ref.exists():
            # modelos de imagem-para-imagem do fal aceitam image_url (data URI funciona)
            mime = "image/png" if ref.suffix.lower() == ".png" else "image/jpeg"
            body["image_url"] = f"data:{mime};base64,{base64.b64encode(ref.read_bytes()).decode()}"
        r = self.http.post(f"https://fal.run/{self.model}", json=body)
        r.raise_for_status()
        url = r.json()["images"][0]["url"]
        if url.startswith("data:"):
            return base64.b64decode(url.split(",", 1)[1])
        return self.http.get(url).content


class FakeImage:
    """Gradiente com ruído, determinístico pelo prompt. Para testes e --dry-run."""

    def generate(self, prompt: str, width: int, height: int, ref: Path | None = None) -> bytes:
        import io
        import random

        from PIL import Image, ImageDraw, ImageFilter

        rnd = random.Random(prompt)
        top = (rnd.randint(10, 60), rnd.randint(30, 80), rnd.randint(10, 50))
        bottom = (rnd.randint(120, 200), rnd.randint(120, 190), rnd.randint(40, 90))
        img = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(img)
        for y in range(height):
            t = y / max(1, height - 1)
            draw.line([(0, y), (width, y)], fill=tuple(int(a + (b - a) * t) for a, b in zip(top, bottom)))
        for _ in range(40):
            x, y = rnd.randrange(width), rnd.randrange(height)
            r = rnd.randint(4, 40)
            draw.ellipse([x - r, y - r, x + r, y + r], fill=(240, 240, 200))
        img = img.filter(ImageFilter.GaussianBlur(6))
        buf = io.BytesIO()
        img.save(buf, "PNG")
        return buf.getvalue()


def make_image_gen(provider: str, model: str) -> ImageGen:
    if provider == "fake":
        return FakeImage()
    if provider == "fal":
        return FalImage(model)
    raise NotImplementedError(f"provedor de imagem '{provider}' ainda não implementado (etapa 2)")
