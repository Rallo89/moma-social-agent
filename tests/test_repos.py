import datetime as dt

import pytest

from mtg_social.errors import NoDataError
from mtg_social.repos import (
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
