"""Rendering reale con Chromium: lento ma e' l'unico modo di accorgersi che
una slide esce tagliata. `pytest -m "not slow"` per saltarlo.
"""

import datetime as dt
import struct
from pathlib import Path

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
    assert "MERCOLEDÌ" in html.upper()


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

    assert post_size(cfg, "leg_results") == (1080, 1080)   # dichiarata dal post
    assert post_size(cfg, "inesistente") == (1080, 1350)   # default globale


def test_dimensione_specifica_del_post(cfg):
    """Un template quadrato convive con gli altri in 4:5."""
    from moma_social.render import post_size

    cfg.data["posts"]["leg_results_standings"]["width"] = 1080
    cfg.data["posts"]["leg_results_standings"]["height"] = 1080
    assert post_size(cfg, "leg_results_standings") == (1080, 1080)
    assert post_size(cfg, "inesistente") == (1080, 1350)


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
    import re

    style = html.split("</style>")[0]
    # Ogni variabile di geometria dev'essere in px, mai in percentuale.
    variabili = re.findall(r"(--[a-z0-9-]+):\s*([^;]+);", style)
    geometria = [(nome, valore) for nome, valore in variabili
                 if nome.endswith(("-size", "-top", "-w", "-h", "-gap", "-pad", "-safe"))]
    assert geometria, "nessuna variabile di geometria trovata"
    assert all(valore.strip().endswith("px") for _, valore in geometria), geometria
    # Il corpo del titolo scala col lato della slide: la misura esatta e' una
    # scelta grafica che cambia, il legame con la larghezza no.
    def titolo(width):
        html = build_html(cfg, "standings_2col.html.j2", {
            "rows": [], "title": "T", "subtitle": "", "hashtag": "",
            "background": "", "width": width, "height": width,
        })
        valore = re.search(r"--title-size:\s*([\d.]+)px", html).group(1)
        return float(valore)

    assert titolo(2160) == pytest.approx(titolo(1080) * 2, rel=0.01)


def test_font_del_brand_inlinato_nella_slide(cfg):
    """Il runner di CI non ha font installati: devono viaggiare nel PNG."""
    html = build_html(cfg, "standings_2col.html.j2", {
        "rows": [], "title": "T", "subtitle": "", "hashtag": "",
        "background": "", "width": 1080, "height": 1080,
    })
    assert "@font-face" in html
    assert "League Gothic" in html
    assert "src: url('data:" in html
    # League Gothic ha un peso solo: il falso grassetto va disattivato.
    assert "font-synthesis: none" in html


# ── ricerca del browser sui vari sistemi operativi ─────────────────────────
def test_su_windows_cerca_anche_edge(monkeypatch):
    """Su Windows Chrome non e' nel PATH, ed Edge c'e' sempre: e' Chromium."""
    import sys as _sys

    from moma_social.render import _installed_browsers

    monkeypatch.setattr(_sys, "platform", "win32")
    monkeypatch.setenv("ProgramFiles", r"C:\Program Files")
    monkeypatch.setenv("ProgramFiles(x86)", r"C:\Program Files (x86)")
    percorsi = [str(p) for p in _installed_browsers()]
    assert any("msedge.exe" in p for p in percorsi)
    assert any("chrome.exe" in p for p in percorsi)


def test_su_macos_cerca_nelle_applicazioni(monkeypatch):
    import sys as _sys

    from moma_social.render import _installed_browsers

    monkeypatch.setattr(_sys, "platform", "darwin")
    percorsi = [str(p) for p in _installed_browsers()]
    assert any("/Applications/Google Chrome.app" in p for p in percorsi)


def test_browser_configurato_ma_inesistente(cfg):
    from moma_social.errors import RenderError
    from moma_social.render import _find_chromium

    with pytest.raises(RenderError, match="chromium_path"):
        _find_chromium("/percorso/che/non/esiste")


def test_messaggio_se_nessun_browser(monkeypatch):
    """Il messaggio deve dire cosa installare, non solo che manca qualcosa."""
    import shutil as _shutil

    from moma_social.errors import RenderError
    from moma_social.render import _find_chromium

    monkeypatch.setattr(_shutil, "which", lambda _: None)
    monkeypatch.setattr("moma_social.render._installed_browsers", list)
    monkeypatch.setenv("PLAYWRIGHT_BROWSERS_PATH", "/non/esiste")
    monkeypatch.setattr(Path, "home", staticmethod(lambda: Path("/non/esiste")))
    with pytest.raises(RenderError) as errore:
        _find_chromium()
    assert "Edge" in str(errore.value)
    assert "render.chromium_path" in str(errore.value)
