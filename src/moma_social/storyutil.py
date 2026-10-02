"""Esportazione JPEG delle storie nel formato richiesto da Meta."""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from .errors import RenderError


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
