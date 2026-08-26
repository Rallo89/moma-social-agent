"""Tempo, fusi orari e settimane.

Tutto il progetto ragiona in ora locale dell'organizzazione (default
Europe/Rome). GitHub Actions gira in UTC: la conversione avviene solo qui.
"""

from __future__ import annotations

import datetime as dt
import re
from zoneinfo import ZoneInfo

from dateutil import parser as _dateparser

from .errors import MtgSocialError

WEEKDAYS_IT = [
    "Lunedi", "Martedi", "Mercoledi", "Giovedi", "Venerdi", "Sabato", "Domenica",
]
MONTHS_IT = [
    "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
    "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre",
]
WEEKDAY_NAMES = {
    "monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3,
    "friday": 4, "saturday": 5, "sunday": 6,
}


def tz(name: str = "Europe/Rome") -> ZoneInfo:
    return ZoneInfo(name)


def now(timezone: str = "Europe/Rome") -> dt.datetime:
    return dt.datetime.now(tz(timezone))


def today(timezone: str = "Europe/Rome") -> dt.date:
    return now(timezone).date()


def parse_date(value, dayfirst: bool = True) -> dt.date | None:
    """Accetta date ISO, italiane (gg/mm/aaaa), datetime, epoch. None se vuoto."""
    if value is None or value == "":
        return None
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    if isinstance(value, (int, float)):
        return dt.datetime.fromtimestamp(value, dt.UTC).date()
    text = str(value).strip()
    if not text:
        return None
    # ISO prima di tutto: con dayfirst=True dateutil leggerebbe "2026-03-11"
    # come 3 novembre. Il pattern ISO non e' ambiguo, non va indovinato.
    iso = re.match(r"^(\d{4})-(\d{2})-(\d{2})", text)
    if iso:
        return dt.date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3)))
    try:
        return _dateparser.parse(text, dayfirst=dayfirst).date()
    except (ValueError, OverflowError) as exc:
        raise MtgSocialError(f"Data non riconosciuta: {value!r}") from exc


def resolve_date(token: str | None, timezone: str = "Europe/Rome") -> dt.date:
    """Risolve 'today' / 'yesterday' / 'tomorrow' / ISO in una data concreta."""
    ref = today(timezone)
    if not token or token == "today":
        return ref
    if token == "yesterday":
        return ref - dt.timedelta(days=1)
    if token == "tomorrow":
        return ref + dt.timedelta(days=1)
    return parse_date(token)


def week_bounds(day: dt.date, week_start: str = "monday") -> tuple[dt.date, dt.date]:
    """Lunedi-domenica della settimana che contiene `day` (estremi inclusi)."""
    offset = WEEKDAY_NAMES[week_start]
    start = day - dt.timedelta(days=(day.weekday() - offset) % 7)
    return start, start + dt.timedelta(days=6)


def fmt_date(day: dt.date, with_weekday: bool = False) -> str:
    """'12 marzo' oppure 'Mercoledi 12 marzo'."""
    base = f"{day.day} {MONTHS_IT[day.month - 1]}"
    return f"{WEEKDAYS_IT[day.weekday()]} {base}" if with_weekday else base


def fmt_range(start: dt.date, end: dt.date) -> str:
    """'12 - 18 marzo' comprimendo il mese quando coincide."""
    if start.month == end.month and start.year == end.year:
        return f"{start.day} - {end.day} {MONTHS_IT[end.month - 1]}"
    return f"{fmt_date(start)} - {fmt_date(end)}"


def weekday_it(day: dt.date) -> str:
    return WEEKDAYS_IT[day.weekday()]
