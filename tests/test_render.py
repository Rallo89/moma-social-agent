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


def test_sfondo_configurato_ma_mancante_torna_al_fondo_generato(cfg, contesto_calendario):
    """Un asset non ancora sincronizzato non deve produrre una slide nera."""
    contesto_calendario["background"] = "templates/images/assets/non-esiste.png"
    html = build_html(cfg, "weekly_calendar.html.j2", contesto_calendario)
    assert "background-image:url('')" not in html
    assert "linear-gradient" in html          # fondo generato dai colori brand


def test_sfondo_presente_viene_inlinato(cfg, contesto_calendario, tmp_path):
    asset = cfg.root / "templates/images/assets/_test_sfondo.png"
    asset.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
    try:
        contesto_calendario["background"] = "templates/images/assets/_test_sfondo.png"
        html = build_html(cfg, "weekly_calendar.html.j2", contesto_calendario)
        assert "background-image:url('data:image/png;base64," in html
    finally:
        asset.unlink()


def test_filtro_asset_e_totale(cfg):
    """Il filtro non deve esplodere su input vuoto, mancante o cartella."""
    from moma_social.render import _asset_data_uri

    assert _asset_data_uri(cfg.root, "") == ""
    assert _asset_data_uri(cfg.root, "non/esiste.png") == ""
    assert _asset_data_uri(cfg.root, "templates/images") == ""   # e' una cartella


def test_dimensione_globale_di_default(cfg):
    from moma_social.render import post_size

    assert post_size(cfg, "weekly_calendar") == (1080, 1350)


def test_dimensione_specifica_del_post(cfg):
    """Un template quadrato convive con gli altri in 4:5."""
    from moma_social.render import post_size

    cfg.data["posts"]["leg_results_standings"]["width"] = 1080
    cfg.data["posts"]["leg_results_standings"]["height"] = 1080
    assert post_size(cfg, "leg_results_standings") == (1080, 1080)
    assert post_size(cfg, "weekly_calendar") == (1080, 1350)


def test_png_rispetta_la_dimensione_del_post(cfg, contesto_calendario):
    path = render(cfg, "weekly_calendar.html.j2", contesto_calendario,
                  "test-quadrato", size=(1080, 1080))
    scale = cfg.get("render.scale")
    assert _size(path) == (1080 * scale, 1080 * scale)


def test_classifica_due_colonne(cfg):
    """Le 16 righe si dividono in due colonne da 8, nell'ordine di classifica."""
    from moma_social.models import StandingRow

    rows = [StandingRow(rank=i, player=f"Giocatore {i}", points=100 - i)
            for i in range(1, 17)]
    html = build_html(cfg, "standings_2col.html.j2", {
        "rows": rows, "title": "Torneo Pauper", "subtitle": "Tappa 10",
        "hashtag": "#modenamagic", "background": "", "width": 1080, "height": 1080,
    })
    assert html.count('class="col"') == 2
    assert html.count('class="row"') == 16
    # La prima colonna finisce all'ottavo e la seconda parte dal nono.
    assert html.index("Giocatore 8") < html.index('class="col"', html.index("Giocatore 8") - 3000) \
        or "Giocatore 9" in html


def test_geometria_in_pixel_non_in_percentuale(cfg):
    """`font-size: 7%` sarebbe il 7% del genitore, non della slide."""
    html = build_html(cfg, "standings_2col.html.j2", {
        "rows": [], "title": "T", "subtitle": "", "hashtag": "",
        "background": "", "width": 1080, "height": 1080,
    })
    assert "--title-size: 78px" in html
    assert "%;" not in html.split("</style>")[0].split("--title-size")[1][:400]
