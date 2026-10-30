"""Esportazione JPEG delle storie nel formato richiesto da Meta."""

from __future__ import annotations

import re
from pathlib import Path

from PIL import Image

from .errors import RenderError


def story_title(title: str, fmt: str) -> dict[str, str]:
    """Separa solo il titolo stagionale riconosciuto; conserva ogni altro nome."""
    match = re.fullmatch(
        rf"{re.escape(fmt)}\s+((?:Fall|Spring|Summer|Winter|Autunno|Primavera|Estate|Inverno)"
        r"\s+\d{4})\s*[-–—:]?\s*(Tappa\s+\d+.*)",
        title.strip(), re.IGNORECASE,
    ) if fmt else None
    if match:
        return {"name": fmt, "season": match[1], "stage": match[2]}
    return {"name": title, "season": "", "stage": ""}


def story_jpeg(png: Path, width: int = 1080, height: int = 1920) -> Path:
    """Esporta un 9:16 reale a 1080x1920, senza stirare o tagliare la card."""
    target = png.with_suffix(".jpg")
    with Image.open(png) as source:
        if source.width * height != source.height * width:
            raise RenderError(f"Proporzioni della storia non 9:16: {source.size}")
        image = source.convert("RGB")
        if image.size != (width, height):
            image = image.resize((width, height), Image.Resampling.LANCZOS)
        image.save(target, "JPEG", quality=90, optimize=True)
    return target
