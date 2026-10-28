"""Aplica texto, contorno e selo do canal sobre a arte gerada, no padrão do YouTube."""
from __future__ import annotations

import io
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

THUMB_SIZE = (1280, 720)
MAX_BYTES = 2 * 1024 * 1024  # limite do YouTube para thumbnails


# fontes com acentos do português, tentadas em ordem se o canal não definir uma
FALLBACK_FONTS = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
    "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
]


def _font(path: Path | None, size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for candidate in [path, *map(Path, FALLBACK_FONTS)]:
        if candidate and candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    # último recurso: a fonte embutida do Pillow não tem Ã, Ç etc.
    return ImageFont.load_default(size=size)


def _wrap(text: str, font, draw: ImageDraw.ImageDraw, max_w: int) -> list[str]:
    words, lines, cur = text.split(), [], ""
    for w in words:
        trial = f"{cur} {w}".strip()
        if draw.textlength(trial, font=font) <= max_w or not cur:
            cur = trial
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def compose(art: bytes | Path, text: str, out: Path, *, font_path: Path | None = None,
            color: str = "#F2E9C9", stroke: str = "#000000", badge: Path | None = None,
            keep_clear: str = "bottom-right") -> Path:
    img = Image.open(art if isinstance(art, Path) else io.BytesIO(art)).convert("RGB")
    img = ImageOps.fit(img, THUMB_SIZE, Image.Resampling.LANCZOS)
    W, H = THUMB_SIZE
    draw = ImageDraw.Draw(img)

    text = text.upper().strip()
    if text:
        # maior fonte que caiba em até 2 linhas na metade esquerda (a direita fica para a arte)
        max_w = int(W * 0.58)
        size = 150
        while size > 40:
            font = _font(font_path, size)
            lines = _wrap(text, font, draw, max_w)
            if len(lines) <= 2 and all(draw.textlength(l, font=font) <= max_w for l in lines):
                break
            size -= 8
        line_h = int(size * 1.05)
        block_h = line_h * len(lines)
        x = 56
        # embaixo à esquerda, longe do selo de duração no canto inferior direito
        y = H - block_h - 64 if keep_clear == "bottom-right" else (H - block_h) // 2
        sw = max(4, size // 12)
        for i, line in enumerate(lines):
            draw.text((x, y + i * line_h), line, font=font, fill=color, stroke_width=sw, stroke_fill=stroke)

    if badge and badge.exists():
        b = Image.open(badge).convert("RGBA")
        b.thumbnail((180, 180))
        img.paste(b, (W - b.width - 40, 40), b)

    out.parent.mkdir(parents=True, exist_ok=True)
    quality = 92
    while True:
        buf = io.BytesIO()
        img.save(buf, "JPEG", quality=quality, optimize=True)
        if buf.tell() <= MAX_BYTES or quality <= 50:
            break
        quality -= 8
    out.write_bytes(buf.getvalue())
    return out
