"""Pipeline di contenuto, con il rendering sostituito da un finto screenshot.

Il rendering vero (Chromium) e' coperto da `test_render.py`, marcato `slow`:
qui interessa la logica di selezione dei dati e il contesto passato ai template.
"""

import datetime as dt
from pathlib import Path

import pytest

from moma_social import pipelines
from moma_social.errors import NoDataError

RENDERED: list[tuple[str, dict]] = []


@pytest.fixture(autouse=True)
def fake_render(monkeypatch, tmp_path):
    RENDERED.clear()

    def _render(cfg, template, context, out_name, size=None):
        RENDERED.append((template, context))
        path = tmp_path / f"{out_name}.png"
        path.write_bytes(b"png")
        return path

    monkeypatch.setattr(pipelines, "render", _render)


def test_calendario_settimanale(cfg):
    """Il lunedi esce un carosello: una card per evento della settimana."""
    draft = pipelines.weekly_calendar(cfg, dt.date(2026, 3, 11))
    assert draft.kind == "weekly_calendar"
    assert draft.meta["events"] == 5
    assert draft.meta["week_start"] == "2026-03-09"
    assert len(draft.images) == 5
    assert draft.is_carousel
    template, context = RENDERED[0]
    assert template == "evento.html.j2"
    # Ogni card porta i suoi slot compilati, non i dati grezzi dell'evento.
    assert context["kicker_1"] == "Calendario settimanale"
    assert context["kicker_2"] == "1/5"
    assert [etichetta for etichetta, _ in context["voci"]] == [
        "Quando", "Dove", "Iscrizione"]


def test_calendario_non_supera_il_limite_della_graph_api(cfg):
    cfg.data["posts"]["weekly_calendar"]["max_carousel_slides"] = 3
    draft = pipelines.weekly_calendar(cfg, dt.date(2026, 3, 11))
    assert len(draft.images) == 3
    assert draft.meta["slide_tagliate"] == 2



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


def test_titolo_e_sottotitolo_delle_due_slide(cfg):
    """La grafica mostra nome torneo e tappa: entrambe le slide li ricevono."""
    pipelines.leg_results(cfg, dt.date(2026, 3, 13), fmt="Pauper")
    tappa, classifica = RENDERED[0][1], RENDERED[1][1]
    assert tappa["title"] == "Torneo Pauper"
    assert tappa["subtitle"] == "Tappa 10"
    assert classifica["title"] == "Torneo Pauper"
    assert classifica["subtitle"] == "Classifica generale"


def test_risultati_sono_un_carosello_di_due_slide(cfg):
    draft = pipelines.leg_results(cfg, dt.date(2026, 3, 11))
    assert draft.is_carousel
    assert len(draft.images) == 2
    # I nomi dei template vengono dalla config: qui conta che siano due,
    # nell'ordine dichiarato.
    assert [t for t, _ in RENDERED] == cfg.get("posts.leg_results.image_templates")
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
        pipelines.leg_results(cfg, dt.date(2026, 3, 10))


def test_densita_cresce_con_le_righe():
    assert pipelines._density(3) == ""
    assert pipelines._density(9) == "dense-8"
    assert pipelines._density(11) == "dense-10"
    assert pipelines._density(20) == "dense-12"


# ── carosello: piu' partecipanti di quanti stiano in una slide ──────────────
def _tappa_con(cfg, monkeypatch, giocatori: int):
    """Sostituisce i risultati di tappa con N giocatori inventati."""
    import datetime as d

    from moma_social.models import LegResults, ResultRow

    leg = LegResults(
        date=d.date(2026, 3, 13), format="Pauper", leg="Tappa 10",
        venue="Modena Magic", players_count=giocatori,
        league="lega-pauper-2026",          # la stessa dei dati di esempio
        rows=[ResultRow(rank=i, player=f"Giocatore {i}", points=(giocatori - i) * 3)
              for i in range(1, giocatori + 1)],
    )
    monkeypatch.setattr(pipelines, "fetch_leg_results", lambda *a, **k: leg)
    return leg


def test_sedici_giocatori_restano_due_slide(cfg, monkeypatch):
    _tappa_con(cfg, monkeypatch, 16)
    draft = pipelines.leg_results(cfg, dt.date(2026, 3, 13), fmt="Pauper")
    assert draft.meta["slide"] == 2
    assert draft.meta["slide_tappa"] == 1


def test_venti_giocatori_diventano_tre_slide(cfg, monkeypatch):
    """Il 17esimo non deve sparire: serve una seconda slide di risultati."""
    _tappa_con(cfg, monkeypatch, 20)
    draft = pipelines.leg_results(cfg, dt.date(2026, 3, 13), fmt="Pauper")
    assert draft.meta["slide_tappa"] == 2
    assert len(draft.images) == 3
    tutti = [r.player for pagina in (RENDERED[0][1]["rows"], RENDERED[1][1]["rows"])
             for r in pagina]
    assert len(tutti) == 20
    assert tutti[16] == "Giocatore 17"


def test_numero_di_pagina_solo_quando_serve(cfg, monkeypatch):
    _tappa_con(cfg, monkeypatch, 20)
    pipelines.leg_results(cfg, dt.date(2026, 3, 13), fmt="Pauper")
    assert RENDERED[0][1]["subtitle"] == "Tappa 10 · 1/2"
    assert RENDERED[1][1]["subtitle"] == "Tappa 10 · 2/2"
    # La classifica sta in una slide sola: niente numerazione.
    assert RENDERED[2][1]["subtitle"] == "Classifica generale"


def test_nomi_dei_file_distinti_fra_le_pagine(cfg, monkeypatch):
    _tappa_con(cfg, monkeypatch, 20)
    draft = pipelines.leg_results(cfg, dt.date(2026, 3, 13), fmt="Pauper")
    assert len(set(draft.images)) == len(draft.images)


def test_carosello_non_supera_il_limite_della_graph_api(cfg, monkeypatch):
    """200 giocatori sarebbero 13 slide: la Graph API ne accetta 10."""
    from moma_social.instagram import MAX_CAROUSEL

    _tappa_con(cfg, monkeypatch, 200)
    draft = pipelines.leg_results(cfg, dt.date(2026, 3, 13), fmt="Pauper")
    assert len(draft.images) <= MAX_CAROUSEL
    assert draft.meta["slide_tagliate"] > 0
    # La classifica cede spazio per prima, ma non sparisce del tutto.
    assert draft.meta["slide_classifica"] >= 1


def test_ordine_delle_slide_risultati_poi_classifica(cfg, monkeypatch):
    _tappa_con(cfg, monkeypatch, 20)
    pipelines.leg_results(cfg, dt.date(2026, 3, 13), fmt="Pauper")
    templates = [t for t, _ in RENDERED]
    attesi = cfg.get("posts.leg_results.image_templates")
    assert templates[:2] == [attesi[0], attesi[0]]   # due pagine di risultati
    assert templates[2] == attesi[1]                 # poi la classifica


# ── la classifica e' facoltativa ────────────────────────────────────────────
def test_senza_classifica_esce_solo_la_tappa(cfg, monkeypatch):
    _tappa_con(cfg, monkeypatch, 16)
    draft = pipelines.leg_results(cfg, dt.date(2026, 3, 13), fmt="Pauper",
                                  senza_classifica=True)
    assert draft.meta["slide_classifica"] == 0
    assert len(draft.images) == 1
    assert "CLASSIFICA GENERALE" not in draft.caption


def test_classifica_assente_non_blocca_il_post(cfg, monkeypatch):
    """Un formato senza lega deve comunque avere il suo post di risultati."""
    _tappa_con(cfg, monkeypatch, 16)
    monkeypatch.setattr(
        pipelines, "fetch_standings",
        lambda *a, **k: (_ for _ in ()).throw(NoDataError("nessuna classifica")),
    )
    draft = pipelines.leg_results(cfg, dt.date(2026, 3, 13), fmt="Pauper")
    assert draft.meta["slide_classifica"] == 0
    assert len(draft.images) == 1


def test_sorgente_giu_non_blocca_la_caption(cfg, monkeypatch):
    """La 'prossima tappa' e' una rifinitura: se la sorgente e' giu', si degrada."""
    from moma_social.errors import SourceError

    _tappa_con(cfg, monkeypatch, 16)
    monkeypatch.setattr(
        pipelines, "fetch_events",
        lambda *a, **k: (_ for _ in ()).throw(SourceError("endpoint irraggiungibile")),
    )
    draft = pipelines.leg_results(cfg, dt.date(2026, 3, 13), fmt="Pauper",
                                  senza_classifica=True)
    assert "in arrivo" in draft.caption


def test_la_classifica_segue_la_lega_della_tappa(cfg, monkeypatch):
    """Non basta il formato: serve la lega, o si prende quella sbagliata."""
    import datetime as d

    from moma_social.models import LegResults, ResultRow

    leg = LegResults(date=d.date(2026, 9, 3), format="Modern", leg="Tappa 5",
                     league="lega-2026",
                     rows=[ResultRow(rank=1, player="X", points=12)])
    monkeypatch.setattr(pipelines, "fetch_leg_results", lambda *a, **k: leg)

    chiamata = {}

    def _standings(cfg_, fmt, **kw):
        chiamata.update(fmt=fmt, **kw)
        from moma_social.models import Standings
        return Standings(format=fmt)

    monkeypatch.setattr(pipelines, "fetch_standings", _standings)
    pipelines.leg_results(cfg, d.date(2026, 9, 3), fmt="Modern")
    assert chiamata["league"] == "lega-2026"


def test_tappa_senza_lega_non_prende_una_classifica_a_caso(cfg, monkeypatch):
    """Senza lega non esiste 'la' classifica: meglio il solo post dei risultati."""
    import datetime as d

    from moma_social.models import LegResults, ResultRow

    leg = LegResults(date=d.date(2026, 9, 3), format="Premodern", leg="Tappa 3",
                     league="",   # torneo non collegato a nessuna lega
                     rows=[ResultRow(rank=1, player="X", points=12)])
    monkeypatch.setattr(pipelines, "fetch_leg_results", lambda *a, **k: leg)

    def _non_deve_essere_chiamata(*a, **k):
        raise AssertionError("senza lega non si deve interrogare la classifica")

    monkeypatch.setattr(pipelines, "fetch_standings", _non_deve_essere_chiamata)
    draft = pipelines.leg_results(cfg, d.date(2026, 9, 3), fmt="Premodern")
    assert draft.meta["slide_classifica"] == 0
    assert len(draft.images) == 1


def test_una_sera_con_due_tornei_produce_due_post(cfg, tmp_path):
    """Il caso reale del 2 settembre: Pauper e Premodern la stessa sera."""
    import json

    righe = [
        {"date": "2026-09-02", "leg": "Lega Pauper Fall 1a tappa",
         "format": "Pauper", "league": "lega-pauper", "rank": posizione,
         "player": nome, "points": str(10 - posizione)}
        for posizione, nome in enumerate(["Anna", "Carla"], start=1)
    ] + [
        {"date": "2026-09-02", "leg": "Premodern Fall tappa 1",
         "format": "Premodern", "league": "lega-premodern", "rank": posizione,
         "player": nome, "points": str(10 - posizione)}
        for posizione, nome in enumerate(["Bruno", "Dario"], start=1)
    ]
    path = tmp_path / "risultati.json"
    path.write_text(json.dumps(righe), encoding="utf-8")
    cfg.data["sources"]["results"] = {"url": str(path), "kind": "json"}

    bozze = pipelines.drafts(cfg, "leg_results", dt.date(2026, 9, 2),
                             senza_classifica=True)
    assert [b.meta["format"] for b in bozze] == ["Pauper", "Premodern"]
    assert [b.meta["winner"] for b in bozze] == ["Anna", "Bruno"]
    # Chiavi di deduplica distinte, altrimenti il secondo post sarebbe scartato
    # come doppione del primo.
    from moma_social.publish import dedupe_key
    assert len({dedupe_key(b) for b in bozze}) == 2


def test_quota_dipende_dal_formato(cfg):
    """Il Pauper non costa come il Limited."""
    def quota(fmt):
        return dict(pipelines._card_evento(cfg, dt.date(2026, 3, 12), fmt)["voci"])[
            "Iscrizione"]

    assert quota("Pauper") == "7 €"
    assert quota("Limited") == "25 €"
    assert quota("Modern") == "10 €"          # default per tutti gli altri


def test_il_link_perde_lo_schema(cfg):
    """La grafica scrive l'indirizzo senza https://, come da istruzioni."""
    assert pipelines._card_evento(cfg, dt.date(2026, 3, 12), "Modern")["link"] == (
        "modena-magic.vercel.app/tornei")


def test_la_card_usa_i_dati_dell_evento_quando_ci_sono(cfg):
    """Sede e quota vengono dall'evento; i modelli in config sono il ripiego."""
    from moma_social.models import Event

    evento = Event(date=dt.date(2026, 3, 12), format="Modern", start_time="21:15",
                   venue="Circolo Arcano", city="Modena", entry_fee="8 €")
    voci = dict(pipelines._card_evento(cfg, evento.date, "Modern", evento)["voci"])
    assert voci["Quando"] == "Giovedì 12 marzo, 21:15"
    assert voci["Dove"] == "Circolo Arcano — Modena"
    assert voci["Iscrizione"] == "8 €"

    senza = dict(pipelines._card_evento(cfg, dt.date(2026, 3, 12), "Modern")["voci"])
    assert senza["Quando"] == "Giovedì 12 marzo, 21"        # ora da config
    assert senza["Dove"] == cfg.get("content.evento.dove")
