"""Rendering reale con Chromium: lento ma e' l'unico modo di accorgersi che
una slide esce tagliata. `pytest -m "not slow"` per saltarlo.
"""

import datetime as dt
import struct

import pytest

from moma_social.render import build_html, render
from moma_social.repos import events_by_day, fetch_events

pytestmark = pytest.mark.slow


def _size(path):
    return struct.unpack(">II", path.read_bytes()[16:24])


@pytest.fixture
def contesto_calendario(cfg):
    events = fetch_events(cfg, dt.date(2026, 3, 9), dt.date(2026, 3, 15))
    return {
        "days": events_by_day(events), "periodo": "9 - 15 marzo",
        "events_count": len(events), "formats": ["Modern"],
        "background": "", "density": "",
    }


def test_html_contiene_i_dati(cfg, contesto_calendario):
    html = build_html(cfg, "weekly_calendar.html.j2", contesto_calendario)
    assert "Serata Commander" in html
    assert "MERCOLEDI" in html.upper()


def test_png_ha_la_misura_del_feed(cfg, contesto_calendario):
    path = render(cfg, "weekly_calendar.html.j2", contesto_calendario, "test-calendario")
    width = cfg.get("render.width") * cfg.get("render.scale")
    height = cfg.get("render.height") * cfg.get("render.scale")
    assert _size(path) == (width, height)


def test_html_salvato_accanto_al_png(cfg, contesto_calendario):
    path = render(cfg, "weekly_calendar.html.j2", contesto_calendario, "test-calendario")
    assert path.with_suffix(".html").exists()


def test_footer_dentro_la_slide(cfg, contesto_calendario):
    """La fascia bassa della slide deve contenere il footer, non il vuoto.

    E' la regressione che il layout a griglia ha risolto: con un flex il
    contenuto lungo spingeva handle e sito fuori dall'immagine.
    """
    from moma_social.pngutil import _decode

    path = render(cfg, "weekly_calendar.html.j2", contesto_calendario, "test-footer")
    width, height, _, pixels = _decode(path)
    band_start = int(height * 0.90)          # ultimo 10% dell'immagine
    band = pixels[band_start * width * 3:]
    # Il testo del footer e' chiaro sul fondo scuro: senza pixel chiari qui
    # significa che il footer e' finito fuori dalla slide.
    assert any(band[i] > 180 for i in range(0, len(band), 3))
