"""Asset delle storie: QR incorporato e JPEG nel formato richiesto da Meta."""

from __future__ import annotations

import base64
import io
from pathlib import Path

import qrcode
from PIL import Image

from .errors import RenderError


def qr_data_uri(url: str) -> str:
    code = qrcode.QRCode(
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=12,
        border=4,
    )
    code.add_data(url)
    code.make(fit=True)
    image = code.make_image(fill_color="#14171a", back_color="white")
    stream = io.BytesIO()
    image.save(stream, format="PNG")
    return "data:image/png;base64," + base64.b64encode(stream.getvalue()).decode("ascii")


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
