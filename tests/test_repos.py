import datetime as dt

import pytest

from moma_social.errors import NoDataError
from moma_social.repos import (
    fetch_events,
    fetch_leg_results,
    fetch_standings,
    formats_on,
    same_format,
)

WEEK_START = dt.date(2026, 3, 9)
WEEK_END = dt.date(2026, 3, 15)


def test_eventi_della_settimana(cfg):
    events = fetch_events(cfg, WEEK_START, WEEK_END)
    assert len(events) == 5
    assert [e.date for e in events] == sorted(e.date for e in events)


def test_eventi_fuori_periodo_esclusi(cfg):
    events = fetch_events(cfg, dt.date(2026, 3, 11), dt.date(2026, 3, 11))
    assert [e.format for e in events] == ["Modern"]


def test_settimana_vuota_solleva_nodata(cfg):
    with pytest.raises(NoDataError):
        fetch_events(cfg, dt.date(2030, 1, 1), dt.date(2030, 1, 7))


def test_formati_distinti_in_ordine(cfg):
    events = fetch_events(cfg, WEEK_START, WEEK_END)
    assert formats_on(events) == ["Commander", "Modern", "Pioneer", "Limited"]


@pytest.mark.parametrize(
    "a,b",
    [("Modern", "modern"), ("Pioneer ", "pioneer"), ("Mono Green", "mono-green")],
)
def test_confronto_formati_tollerante(a, b):
    assert same_format(a, b)


def test_confronto_formati_vuoti():
    assert not same_format("", "Modern")


def test_risultati_di_tappa(cfg):
    leg = fetch_leg_results(cfg, dt.date(2026, 3, 11))
    assert leg.format == "Modern"
    assert leg.leg == "Tappa 4"
    assert leg.players_count == 12
    assert leg.winner.player == "Marco Bianchi"
    assert [r.rank for r in leg.rows] == list(range(1, 13))


def test_risultati_filtrati_per_formato(cfg):
    leg = fetch_leg_results(cfg, dt.date(2026, 3, 12), "Pioneer")
    assert leg.format == "Pioneer"


def test_risultati_formato_sbagliato(cfg):
    with pytest.raises(NoDataError):
        fetch_leg_results(cfg, dt.date(2026, 3, 11), "Pioneer")


def test_classifica_ordinata(cfg):
    standings = fetch_standings(cfg, "Modern")
    assert standings.season == "2025/26"
    assert [r.rank for r in standings.rows] == sorted(r.rank for r in standings.rows)


def test_classifica_formato_inesistente(cfg):
    with pytest.raises(NoDataError):
        fetch_standings(cfg, "Vintage")


# ── record: i pareggi non si perdono ────────────────────────────────────────
def test_record_composto_dai_tre_numeri(cfg, monkeypatch, tmp_path):
    """Un 3-0-1 non deve diventare 3-0: e' il bug visto sul primo post reale."""
    import json

    sorgente = tmp_path / "risultati.json"
    sorgente.write_text(json.dumps([
        {"date": "2026-09-03", "format": "Modern", "rank": 1,
         "player": "Tianguang Liu", "wins": 3, "losses": 0, "draws": 1},
        {"date": "2026-09-03", "format": "Modern", "rank": 2,
         "player": "Altro Giocatore", "wins": 3, "losses": 1, "draws": 0},
    ]), encoding="utf-8")
    cfg.data["sources"]["results"] = {"url": str(sorgente), "kind": "json"}

    leg = fetch_leg_results(cfg, dt.date(2026, 9, 3))
    assert leg.rows[0].record == "3-0-1"
    assert leg.rows[1].record == "3-1"       # zero pareggi: non si scrive "3-1-0"


def test_record_gia_pronto_ha_la_precedenza(cfg, monkeypatch, tmp_path):
    """Una sorgente che espone la stringa gia' fatta non va sovrascritta."""
    import json

    sorgente = tmp_path / "risultati.json"
    sorgente.write_text(json.dumps([
        {"date": "2026-09-03", "format": "Modern", "rank": 1, "player": "X",
         "record": "5-0", "wins": 3, "losses": 0, "draws": 1},
    ]), encoding="utf-8")
    cfg.data["sources"]["results"] = {"url": str(sorgente), "kind": "json"}

    assert fetch_leg_results(cfg, dt.date(2026, 9, 3)).rows[0].record == "5-0"


@pytest.mark.parametrize(
    "vinte,perse,pari,atteso",
    [(3, 0, 1, "3-0-1"), (3, 0, 0, "3-0"), (4, 1, None, "4-1"),
     (0, 3, 2, "0-3-2"), ("", "", "", ""), (None, 2, 0, "")],
)
def test_formattazione_record(vinte, perse, pari, atteso):
    from moma_social.models import format_record

    assert format_record(vinte, perse, pari) == atteso
