import datetime as dt

import pytest

from moma_social.errors import MtgSocialError
from moma_social.timeutil import (
    fmt_range,
    parse_date,
    resolve_date,
    week_bounds,
    weekday_it,
)


@pytest.mark.parametrize(
    "value,expected",
    [
        ("2026-03-11", dt.date(2026, 3, 11)),
        ("11/03/2026", dt.date(2026, 3, 11)),          # uso italiano
        ("2026-03-11T20:30:00Z", dt.date(2026, 3, 11)),
        (dt.date(2026, 3, 11), dt.date(2026, 3, 11)),
        ("", None),
        (None, None),
    ],
)
def test_parse_date(value, expected):
    assert parse_date(value) == expected


def test_parse_date_iso_non_e_ambigua():
    """Con dayfirst=True dateutil leggerebbe 2026-03-11 come 3 novembre."""
    assert parse_date("2026-03-11").month == 3


def test_parse_date_invalida():
    with pytest.raises(MtgSocialError):
        parse_date("non una data")


def test_week_bounds_da_mercoledi():
    start, end = week_bounds(dt.date(2026, 3, 11))
    assert (start, end) == (dt.date(2026, 3, 9), dt.date(2026, 3, 15))


def test_week_bounds_da_domenica():
    start, end = week_bounds(dt.date(2026, 3, 15))
    assert (start, end) == (dt.date(2026, 3, 9), dt.date(2026, 3, 15))


def test_fmt_range_comprime_il_mese():
    assert fmt_range(dt.date(2026, 3, 9), dt.date(2026, 3, 15)) == "9 - 15 marzo"


def test_fmt_range_a_cavallo_di_mese():
    assert fmt_range(dt.date(2026, 3, 30), dt.date(2026, 4, 5)) == "30 marzo - 5 aprile"


def test_weekday_it():
    assert weekday_it(dt.date(2026, 3, 11)) == "Mercoledì"


def test_resolve_yesterday():
    assert resolve_date("yesterday") == dt.date.today() - dt.timedelta(days=1)


def test_fuso_orario_sconosciuto_spiega_cosa_fare():
    """Su Windows manca tzdata: il messaggio deve dirlo, non dare un traceback."""
    from moma_social.errors import ConfigError
    from moma_social.timeutil import tz

    with pytest.raises(ConfigError) as errore:
        tz("Non/Esiste")
    messaggio = str(errore.value)
    assert "tzdata" in messaggio
    assert "org.timezone" in messaggio


def test_fuso_orario_valido():
    from moma_social.timeutil import tz

    assert tz("Europe/Rome").key == "Europe/Rome"
