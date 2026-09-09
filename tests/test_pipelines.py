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
    """Il lunedi: una card di riepilogo, poi una card per evento."""
    draft = pipelines.weekly_calendar(cfg, dt.date(2026, 3, 11))
    assert draft.kind == "weekly_calendar"
    assert draft.meta["events"] == 5
    assert draft.meta["week_start"] == "2026-03-09"
    assert len(draft.images) == 6          # 1 riepilogo + 5 serate
    assert draft.is_carousel

    riepilogo, contesto = RENDERED[0]
    assert riepilogo == "settimana.html.j2"
    assert contesto["badge"] == "9 - 15 marzo"
    assert len(contesto["serate"]) == 5
    assert contesto["serate"][0]["quando"].startswith("Lunedì 9")

    template, context = RENDERED[1]
    assert template == "evento.html.j2"
    # Ogni card porta i suoi slot compilati, non i dati grezzi dell'evento.
    assert context["kicker_1"] == "Calendario settimanale"
    assert context["kicker_2"] == "1/5"
    assert [voce["etichetta"] for voce in context["voci"]] == [
        "Quando", "Dove", "Iscrizione"]


def test_calendario_senza_riepilogo(cfg):
    cfg.data["posts"]["weekly_calendar"]["riepilogo"] = False
    draft = pipelines.weekly_calendar(cfg, dt.date(2026, 3, 11))
    assert len(draft.images) == 5
    assert RENDERED[0][0] == "evento.html.j2"


def test_calendario_non_supera_il_limite_della_graph_api(cfg):
    """Il riepilogo occupa una slide: le serate che restano sono una in meno."""
    cfg.data["posts"]["weekly_calendar"]["max_carousel_slides"] = 3
    draft = pipelines.weekly_calendar(cfg, dt.date(2026, 3, 11))
    assert len(draft.images) == 3          # riepilogo + 2 serate
    assert draft.meta["slide_tagliate"] == 3
    # Il riepilogo elenca solo le serate che il carosello mostra davvero.
    assert len(RENDERED[0][1]["serate"]) == 2



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


def test_le_due_slide_usano_gli_slot_della_card(cfg):
    """Risultati e classifica parlano la lingua delle card del calendario."""
    pipelines.leg_results(cfg, dt.date(2026, 3, 13), fmt="Pauper")
    tappa, classifica = RENDERED[0][1], RENDERED[1][1]
    assert RENDERED[0][0] == RENDERED[1][0] == "classifica.html.j2"

    assert tappa["badge"] == "Pauper"
    assert tappa["kicker_1"] == "Risultati di tappa"
    assert tappa["titolo"] == "Tappa 10"        # letto dal nome del torneo
    assert tappa["righe"][0].player

    assert classifica["badge"] == "Pauper"
    assert classifica["kicker_1"] == "Classifica generale"
    assert classifica["titolo"] == "Classifica"

    # Il vecchio template su sfondo Canva resta selezionabile e coerente.
    assert tappa["subtitle"] == "Tappa 10"
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
    assert RENDERED[0][1]["kicker_2"] == "1/2"
    assert RENDERED[1][1]["kicker_2"] == "2/2"
    # La classifica sta in una slide sola: al posto del numero, la data.
    assert RENDERED[2][1]["kicker_2"] == "13 marzo"


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
        return _voci(pipelines._card_evento(cfg, dt.date(2026, 3, 12), fmt))[
            "Iscrizione"]

    assert quota("Pauper") == "7 €"
    assert quota("Limited") == "25 €"
    assert quota("Modern") == "10 €"          # default per tutti gli altri


def test_il_link_perde_lo_schema(cfg):
    """La grafica scrive l'indirizzo senza https://, come da istruzioni."""
    assert pipelines._card_evento(cfg, dt.date(2026, 3, 12), "Modern")["link"] == (
        "modena-magic.vercel.app/tornei")


def _voci(card):
    return {voce["etichetta"]: voce["valore"] for voce in card["voci"]}


def test_la_card_usa_i_dati_dell_evento_quando_ci_sono(cfg):
    """Sede e quota vengono dall'evento; i modelli in config sono il ripiego."""
    from moma_social.models import Event

    evento = Event(date=dt.date(2026, 3, 12), format="Modern", start_time="21:15",
                   venue="Circolo Arcano", city="Modena", entry_fee="8 €",
                   title="Tappa 4 - Modern League")
    card = pipelines._card_evento(cfg, evento.date, "Modern", evento)
    # Il titolo e' il nome del torneo a database, non un'etichetta costruita.
    assert card["titolo"] == "Tappa 4 - Modern League"
    voci = _voci(card)
    assert voci["Quando"] == "Giovedì 12 marzo, 21:15"
    assert voci["Dove"] == "Circolo Arcano"
    assert voci["Iscrizione"] == "8 €"

    senza = pipelines._card_evento(cfg, dt.date(2026, 3, 12), "Modern")
    assert senza["titolo"] == "Giovedì Modern"              # nessun evento
    assert _voci(senza)["Quando"] == "Giovedì 12 marzo, 21:00"


def test_l_indirizzo_segue_la_sede(cfg):
    """L'indirizzo in config vale per la sede abituale, non per un'altra."""
    from moma_social.models import Event

    def dettaglio(venue):
        evento = Event(date=dt.date(2026, 3, 12), format="Modern", venue=venue)
        card = pipelines._card_evento(cfg, evento.date, "Modern", evento)
        return next(v for v in card["voci"] if v["etichetta"] == "Dove").get(
            "dettaglio", "")

    assert dettaglio("Uno Critico") == cfg.get("content.evento.indirizzo")
    # Sede diversa: meglio nessun indirizzo che quello sbagliato.
    assert dettaglio("Palazzetto Fiera") == ""


def test_titolo_di_una_tappa_di_lega(cfg):
    """Lega e numero: il titolo resta uguale ogni settimana."""
    from moma_social.models import Event

    evento = Event(date=dt.date(2026, 3, 12), format="Modern",
                   title="Modern Fall tappa 3 - recupero",
                   league="Lega Modern Fall", stage="3")
    card = pipelines._card_evento(cfg, evento.date, "Modern", evento)
    assert card["sopratitolo"] == "Lega Modern Fall"
    assert card["titolo"] == "Tappa 3"


def test_evento_spot_tiene_il_proprio_nome(cfg):
    """Senza lega non c'e' nessuna tappa da numerare: vale il nome dell'evento."""
    from moma_social.models import Event

    evento = Event(date=dt.date(2026, 3, 14), format="Limited",
                   title="Prerelease Edge of Eternities")
    card = pipelines._card_evento(cfg, evento.date, "Limited", evento)
    assert card["sopratitolo"] == ""
    assert card["titolo"] == "Prerelease Edge of Eternities"


def test_lega_senza_numero_di_tappa_non_inventa_la_tappa(cfg):
    """Meglio il nome del torneo che un "Tappa" senza numero."""
    from moma_social.models import Event

    evento = Event(date=dt.date(2026, 3, 12), format="Modern",
                   title="Modern Fall tappa 3", league="Lega Modern Fall")
    card = pipelines._card_evento(cfg, evento.date, "Modern", evento)
    assert card["sopratitolo"] == ""
    assert card["titolo"] == "Modern Fall tappa 3"


def test_la_quota_del_database_vince_su_quella_di_configurazione(cfg):
    """Un numero a database diventa "7 €"; il testo scritto a mano resta com'e'."""
    from moma_social.models import Event, format_fee

    assert format_fee("7") == "7 €"
    assert format_fee(7.0) == "7 €"
    assert format_fee("7.50") == "7,50 €"
    assert format_fee("Gratis") == "Gratis"      # gia' scritto per esteso
    assert format_fee("") == ""

    evento = Event(date=dt.date(2026, 3, 12), format="Pauper", entry_fee="12")
    card = pipelines._card_evento(cfg, evento.date, "Pauper", evento)
    assert _voci(card)["Iscrizione"] == "12 €"   # non i 7 € del ripiego


def test_numero_di_tappa_letto_dal_nome_del_torneo(cfg):
    """I nomi veri sono scritti a mano: dieci forme diverse, tutte da capire."""
    from moma_social.models import stage_from_title

    assert stage_from_title("Modern Fall tappa 1") == ("1", False)
    assert stage_from_title("Limited Spring 2025 Tappa 5 - TAV. C") == ("5", False)
    assert stage_from_title("Limited spring 26  quinta tappa") == ("5", False)
    assert stage_from_title("Legacy Tappa 1 -Recupero") == ("1", False)
    # L'anno non e' un numero di tappa, ne' scritto per esteso ne' abbreviato.
    assert stage_from_title("Lega Pauper Fall 1° tappa 2026") == ("1", False)
    assert stage_from_title("Limited Winter 2023 Tappa 1") == ("1", False)
    assert stage_from_title("Premodern Spring '26 tappa 8") == ("8", False)
    # Le finali si dichiarano finali, non si numerano.
    assert stage_from_title("Finale Legacy Autumn 2025") == ("", True)
    assert stage_from_title("Limited Winter 2023 Finale") == ("", True)
    # Quello che non si riconosce resta senza numero, non ne inventa uno.
    assert stage_from_title("Prerelease Strixhaven - TAV. B") == ("", False)


def test_titolo_di_una_finale(cfg):
    from moma_social.models import Event

    evento = Event(date=dt.date(2026, 7, 10), format="Modern",
                   title="Finale Modern Spring 2026",
                   league="Modern Spring 2026", is_final=True)
    card = pipelines._card_evento(cfg, evento.date, "Modern", evento)
    assert card["sopratitolo"] == "Modern Spring 2026"
    assert card["titolo"] == "Finale"


def test_i_tavoli_della_stessa_tappa_sono_una_card_sola(cfg):
    """A database sono tre tornei; per chi legge il calendario e' una serata."""
    from moma_social.models import Event

    def tavolo(lettera):
        return Event(date=dt.date(2026, 4, 23), format="Limited",
                     title=f"Limited Spring 2026 Tappa 2 - TAV. {lettera}",
                     league="Limited Spring 2026", stage="2")

    eventi = [tavolo("A"), tavolo("B"), tavolo("C"),
              Event(date=dt.date(2026, 4, 23), format="Modern",
                    title="Modern Spring 2026 Tappa 5",
                    league="Modern Spring 2026", stage="5")]
    unici = pipelines._una_card_per_tappa(eventi)
    assert [e.format for e in unici] == ["Limited", "Modern"]


def _serata(cfg, **kw):
    from moma_social.models import Event
    return pipelines._serata(cfg, Event(date=dt.date(2026, 9, 17), **kw))


def test_riga_della_settimana_mette_il_formato_in_testa(cfg):
    """In un calendario si cerca il formato: sta all'inizio di ogni riga."""
    assert _serata(cfg, format="Modern", league="Modern Fall 2026",
                   stage="2")["cosa"] == "Modern · Tappa 2"
    assert _serata(cfg, format="Pauper", league="Pauper fall 2026",
                   is_final=True)["cosa"] == "Pauper · Finale"
    # Uno spot porta il proprio nome, ma il formato resta in testa.
    assert _serata(cfg, format="Limited", title="Prerelease Edge of Eternities"
                   )["cosa"] == "Limited · Prerelease Edge of Eternities"
    # Tranne quando il nome lo dice gia': "Commander · Serata Commander" no.
    assert _serata(cfg, format="Commander", title="Serata Commander"
                   )["cosa"] == "Serata Commander"


def test_riga_della_settimana_usa_l_ora_di_configurazione(cfg):
    assert _serata(cfg, format="Modern")["quando"] == "Giovedì 17 · 21:00"
    assert _serata(cfg, format="Modern", start_time="15:00"
                   )["quando"] == "Giovedì 17 · 15:00"


def test_calendario_mensile_guarda_al_mese_dopo(cfg):
    """Gira il 30 e annuncia il mese successivo, non quello in corso."""
    cfg.data["sources"]["events"] = {"url": "data/samples/events.json",
                                     "kind": "auto"}
    draft = pipelines.monthly_calendar(cfg, dt.date(2026, 2, 28))
    assert draft.kind == "monthly_calendar"
    assert draft.meta["month_start"] == "2026-03-01"
    assert draft.meta["month_end"] == "2026-03-31"
    template, contesto = RENDERED[0]
    assert template == "settimana.html.j2"
    assert contesto["badge"] == "marzo 2026"


def test_calendario_mensile_impagina_invece_di_rimpicciolire(cfg):
    """Un mese pieno non entra leggibile in una slide sola."""
    cfg.data["sources"]["events"] = {"url": "data/samples/events.json",
                                     "kind": "auto"}
    cfg.data["posts"]["monthly_calendar"]["rows_per_slide"] = 2
    draft = pipelines.monthly_calendar(cfg, dt.date(2026, 2, 28))
    assert len(draft.images) == 3          # 5 eventi, 2 per slide
    assert RENDERED[0][1]["kicker_2"] == "1/3"
    assert len(RENDERED[0][1]["serate"]) == 2
