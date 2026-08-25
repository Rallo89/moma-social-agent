import struct
import zlib

import pytest

from mtg_social.errors import RenderError
from mtg_social.pngutil import crop_top_left


def _write_png(path, width, height, color=(200, 30, 30)):
    raw = b"".join(b"\x00" + bytes(color) * width for _ in range(height))

    def chunk(tag, payload):
        return (struct.pack(">I", len(payload)) + tag + payload
                + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))

    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )


def _size(path):
    return struct.unpack(">II", path.read_bytes()[16:24])


def test_ritaglia_in_altezza(tmp_path):
    png = tmp_path / "a.png"
    _write_png(png, 100, 160)
    crop_top_left(png, 100, 120)
    assert _size(png) == (100, 120)


def test_ritaglia_in_larghezza_e_altezza(tmp_path):
    png = tmp_path / "a.png"
    _write_png(png, 100, 160)
    crop_top_left(png, 60, 120)
    assert _size(png) == (60, 120)


def test_no_op_se_gia_della_misura(tmp_path):
    png = tmp_path / "a.png"
    _write_png(png, 80, 80)
    before = png.read_bytes()
    crop_top_left(png, 80, 80)
    assert png.read_bytes() == before


def test_non_ingrandisce(tmp_path):
    png = tmp_path / "a.png"
    _write_png(png, 40, 40)
    crop_top_left(png, 100, 100)
    assert _size(png) == (40, 40)


def test_file_non_png(tmp_path):
    path = tmp_path / "a.png"
    path.write_bytes(b"non un png")
    with pytest.raises(RenderError):
        crop_top_left(path, 10, 10)
