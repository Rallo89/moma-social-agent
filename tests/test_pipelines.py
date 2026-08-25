"""Pipeline di contenuto, con il rendering sostituito da un finto screenshot.

Il rendering vero (Chromium) e' coperto da `test_render.py`, marcato `slow`:
qui interessa la logica di selezione dei dati e il contesto passato ai template.
"""

import datetime as dt
from pathlib import Path

import pytest

from mtg_social import pipelines
from mtg_social.errors import NoDataError

RENDERED: list[tuple[str, dict]] = []


@pytest.fixture(autouse=True)
def fake_render(monkeypatch, tmp_path):
    RENDERED.clear()

    def _render(cfg, template, context, out_name):
        RENDERED.append((template, context))
        path = tmp_path / f"{out_name}.png"
        path.write_bytes(b"png")
        return path

    monkeypatch.setattr(pipelines, "render", _render)


def test_calendario_settimanale(cfg):
    draft = pipelines.weekly_calendar(cfg, dt.date(2026, 3, 11))
    assert draft.kind == "weekly_calendar"
    assert not draft.is_carousel
    assert draft.meta["events"] == 5
    assert draft.meta["week_start"] == "2026-03-09"
    template, context = RENDERED[0]
    assert template == "weekly_calendar.html.j2"
    assert len(context["days"]) == 5


def test_calendario_senza_eventi(cfg):
    with pytest.raises(NoDataError):
        pipelines.weekly_calendar(cfg, dt.date(2030, 1, 1))


def test_formato_dedotto_dal_calendario(cfg):
    draft = pipelines.format_spotlight(cfg, dt.date(2026, 3, 11))
    assert draft.meta["format"] == "Modern"
    assert "Modern" in draft.caption


def test_formato_forzato(cfg):
    draft = pipelines.format_spotlight(cfg, dt.date(2026, 3, 12), fmt="Pioneer")
    assert draft.meta["format"] == "Pioneer"


def test_formato_fallback_da_config(cfg):
    """Giorno senza eventi ma con un formato di riserva: il post esce lo stesso."""
    cfg.data["content"]["formats_by_weekday"]["monday"] = "Commander"
    draft = pipelines.format_spotlight(cfg, dt.date(2030, 1, 7))  # e' un lunedi
    assert draft.meta["format"] == "Commander"
    assert draft.meta["events"] == 0


def test_formato_senza_eventi_ne_fallback(cfg):
    cfg.data["content"]["formats_by_weekday"] = {}
    with pytest.raises(NoDataError):
        pipelines.format_spotlight(cfg, dt.date(2030, 1, 7))


def test_risultati_sono_un_carosello_di_due_slide(cfg):
    draft = pipelines.leg_results(cfg, dt.date(2026, 3, 11))
    assert draft.is_carousel
    assert len(draft.images) == 2
    assert [t for t, _ in RENDERED] == ["leg_results.html.j2", "standings.html.j2"]
    # L'ordine del carosello e' parte del contenuto: prima la tappa, poi la classifica.
    assert "risultati" in Path(draft.images[0]).name
    assert "classifica" in Path(draft.images[1]).name


def test_risultati_rispettano_i_limiti_di_righe(cfg):
    cfg.data["posts"]["leg_results"]["top_n"] = 4
    cfg.data["posts"]["leg_results"]["standings_top_n"] = 6
    pipelines.leg_results(cfg, dt.date(2026, 3, 11))
    assert len(RENDERED[0][1]["rows"]) == 4
    assert len(RENDERED[1][1]["rows"]) == 6


def test_risultati_default_e_ieri(cfg, monkeypatch):
    monkeypatch.setattr(pipelines, "resolve_date", lambda token, tz: dt.date(2026, 3, 12))
    draft = pipelines.leg_results(cfg)
    assert draft.meta["format"] == "Pioneer"


def test_risultati_tappa_non_caricata(cfg):
    with pytest.raises(NoDataError):
        pipelines.leg_results(cfg, dt.date(2026, 3, 13))


def test_densita_cresce_con_le_righe():
    assert pipelines._density(3) == ""
    assert pipelines._density(9) == "dense-8"
    assert pipelines._density(11) == "dense-10"
    assert pipelines._density(20) == "dense-12"
