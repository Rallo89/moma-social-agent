"""Ritaglio PNG senza dipendenze native.

Serve al backend "chromium": `chrome --headless --screenshot` produce
un'immagine alta quanto la *finestra*, ma dipinge solo il viewport, che in
headless e' piu' basso di qualche decina di pixel (spazio riservato alla UI
del browser). Si chiede quindi una finestra abbondante e si ritaglia il
risultato alla misura esatta della slide, invece di inseguire un offset che
cambia da una versione di Chrome all'altra.

Supporta PNG a 8 bit, truecolor con o senza alpha: e' esattamente quello che
Chrome scrive.
"""

from __future__ import annotations

import struct
import zlib
from pathlib import Path

from .errors import RenderError

CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4}
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"


def _chunk(tag: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + tag + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))


def _decode(path: Path) -> tuple[int, int, int, bytearray]:
    data = path.read_bytes()
    if not data.startswith(PNG_MAGIC):
        raise RenderError(f"{path} non e' un PNG")
    pos, idat, width, height, depth, color = 8, bytearray(), 0, 0, 8, 2
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos + 4])[0]
        tag = data[pos + 4:pos + 8]
        payload = data[pos + 8:pos + 8 + length]
        if tag == b"IHDR":
            width, height, depth, color = struct.unpack(">IIBB", payload[:10])
        elif tag == b"IDAT":
            idat += payload
        pos += 12 + length

    if depth != 8 or color not in CHANNELS:
        raise RenderError(f"PNG non supportato (bit depth {depth}, color type {color})")

    channels = CHANNELS[color]
    stride = width * channels
    raw = zlib.decompress(bytes(idat))
    pixels = bytearray(height * stride)
    previous = bytearray(stride)
    offset = 0
    for row in range(height):
        filter_type = raw[offset]
        offset += 1
        line = bytearray(raw[offset:offset + stride])
        offset += stride
        _unfilter(filter_type, line, previous, channels)
        pixels[row * stride:(row + 1) * stride] = line
        previous = line
    return width, height, color, pixels


def _unfilter(filter_type: int, line: bytearray, previous: bytearray, channels: int) -> None:
    if filter_type == 0:
        return
    for index in range(len(line)):
        left = line[index - channels] if index >= channels else 0
        up = previous[index]
        up_left = previous[index - channels] if index >= channels else 0
        if filter_type == 1:
            line[index] = (line[index] + left) & 0xFF
        elif filter_type == 2:
            line[index] = (line[index] + up) & 0xFF
        elif filter_type == 3:
            line[index] = (line[index] + (left + up) // 2) & 0xFF
        elif filter_type == 4:
            estimate = left + up - up_left
            distances = (abs(estimate - left), abs(estimate - up), abs(estimate - up_left))
            best = min(distances)
            predictor = left if distances[0] == best else (up if distances[1] == best else up_left)
            line[index] = (line[index] + predictor) & 0xFF
        else:
            raise RenderError(f"Filtro PNG sconosciuto: {filter_type}")


def crop_top_left(path: Path, width: int, height: int) -> Path:
    """Ritaglia il PNG alla regione in alto a sinistra width x height.

    No-op se l'immagine e' gia' della misura giusta o piu' piccola.
    """
    source_width, source_height, color, pixels = _decode(path)
    width = min(width, source_width)
    height = min(height, source_height)
    if (width, height) == (source_width, source_height):
        return path

    channels = CHANNELS[color]
    src_stride = source_width * channels
    dst_stride = width * channels
    raw = bytearray()
    for row in range(height):
        start = row * src_stride
        raw += b"\x00" + pixels[start:start + dst_stride]

    path.write_bytes(
        PNG_MAGIC
        + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, color, 0, 0, 0))
        + _chunk(b"IDAT", zlib.compress(bytes(raw), 6))
        + _chunk(b"IEND", b"")
    )
    return path
