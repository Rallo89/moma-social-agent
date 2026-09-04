"""Dai record grezzi ai modelli: filtri, ordinamenti, normalizzazioni.

Il filtro viene *sempre* riapplicato qui in memoria, anche quando la sorgente
supporta i placeholder server-side. Costa poco e rende l'agente immune a un
endpoint che ignora i parametri.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

from .config import Config
from .errors import NoDataError
from .models import Event, LegResults, ResultRow, StandingRow, Standings, format_record
from .sources import load_rows
from .timeutil import parse_date


def _clean(value) -> str:
    return "" if value is None else str(value).strip()


def _as_int(value, default=0) -> int:
    try:
        return int(float(str(value).strip()))
    except (TypeError, ValueError):
        return default


def _norm_format(value: str) -> str:
    """Confronto tra formati tollerante a maiuscole/spazi/accenti d'uso comune."""
    return _clean(value).lower().replace("-", " ").replace("_", " ").strip()


def same_format(a: str, b: str) -> bool:
    return bool(a) and bool(b) and _norm_format(a) == _norm_format(b)


# ── Eventi ──────────────────────────────────────────────────────────────────
def fetch_events(cfg: Config, start: dt.date, end: dt.date) -> list[Event]:
    """Eventi con data compresa fra start ed end (estremi inclusi)."""
    rows = load_rows(
        cfg.section("sources.events"),
        Path(cfg.root),
        date_from=start.isoformat(),
        date_to=end.isoformat(),
        date=start.isoformat(),
        format="",
        season=cfg.get("org.season", ""),
    )
    events: list[Event] = []
    for row in rows:
        day = parse_date(row.get("date"))
        if day is None or not (start <= day <= end):
            continue
        events.append(
            Event(
                date=day,
                title=_clean(row.get("title")),
                format=_clean(row.get("format")),
                start_time=_clean(row.get("start_time")),
                venue=_clean(row.get("venue")),
                city=_clean(row.get("city")),
                entry_fee=_clean(row.get("entry_fee")),
                prize=_clean(row.get("prize")),
                signup_url=_clean(row.get("signup_url")),
                notes=_clean(row.get("notes")),
                extra=row.get("_extra", {}),
            )
        )
    events.sort(key=lambda e: (e.date, e.start_time or "99:99"))
    if not events:
        raise NoDataError(f"Nessun evento fra {start.isoformat()} e {end.isoformat()}")
    return events


def events_by_day(events: list[Event]) -> list[tuple[dt.date, list[Event]]]:
    """Raggruppa per giorno preservando l'ordine cronologico."""
    grouped: dict[dt.date, list[Event]] = {}
    for event in events:
        grouped.setdefault(event.date, []).append(event)
    return sorted(grouped.items())


def formats_on(events: list[Event]) -> list[str]:
    """Formati distinti, nell'ordine in cui compaiono."""
    seen, out = set(), []
    for event in events:
        key = _norm_format(event.format)
        if event.format and key not in seen:
            seen.add(key)
            out.append(event.format)
    return out


# ── Risultati di tappa ──────────────────────────────────────────────────────
def fetch_leg_results(cfg: Config, day: dt.date, fmt: str = "") -> LegResults:
    rows = load_rows(
        cfg.section("sources.results"),
        Path(cfg.root),
        date=day.isoformat(),
        date_from=day.isoformat(),
        date_to=day.isoformat(),
        format=fmt,
        season=cfg.get("org.season", ""),
    )
    selected = []
    for row in rows:
        row_day = parse_date(row.get("date"))
        if row_day != day:
            continue
        if fmt and row.get("format") and not same_format(row.get("format"), fmt):
            continue
        selected.append(row)

    if not selected:
        label = f" ({fmt})" if fmt else ""
        raise NoDataError(f"Nessun risultato per la tappa del {day.isoformat()}{label}")

    head = selected[0]
    results = LegResults(
        date=day,
        format=_clean(head.get("format")) or fmt,
        leg=_clean(head.get("leg")),
        venue=_clean(head.get("venue")),
        players_count=_as_int(head.get("players_count"), default="") or len(selected),
        rows=[
            ResultRow(
                rank=_as_int(row.get("rank"), default=index + 1),
                player=_clean(row.get("player")),
                deck=_clean(row.get("deck")),
                # Se la sorgente espone i tre numeri, la stringa la componiamo
                # noi; un `record` gia' pronto ha comunque la precedenza.
                record=_clean(row.get("record")) or format_record(
                    row.get("wins"), row.get("losses"), row.get("draws")
                ),
                points=_clean(row.get("points")),
                wins=_clean(row.get("wins")),
                losses=_clean(row.get("losses")),
                draws=_clean(row.get("draws")),
                extra=row.get("_extra", {}),
            )
            for index, row in enumerate(selected)
        ],
    )
    results.rows.sort(key=lambda r: r.rank)
    return results


# ── Classifica generale ─────────────────────────────────────────────────────
def fetch_standings(cfg: Config, fmt: str, season: str = "") -> Standings:
    season = season or cfg.get("org.season", "")
    rows = load_rows(
        cfg.section("sources.standings"),
        Path(cfg.root),
        format=fmt,
        season=season,
        date="",
        date_from="",
        date_to="",
    )
    selected = [
        row for row in rows
        if (not row.get("format") or same_format(row.get("format"), fmt))
        and (not season or not row.get("season") or _clean(row.get("season")) == season)
    ]
    if not selected:
        raise NoDataError(f"Nessuna classifica disponibile per il formato '{fmt}'")

    standings = Standings(
        format=fmt,
        season=season or _clean(selected[0].get("season")),
        rows=[
            StandingRow(
                rank=_as_int(row.get("rank"), default=index + 1),
                player=_clean(row.get("player")),
                points=_clean(row.get("points")),
                events_played=_clean(row.get("events_played")),
                delta=_clean(row.get("delta")),
                extra=row.get("_extra", {}),
            )
            for index, row in enumerate(selected)
        ],
    )
    standings.rows.sort(key=lambda r: r.rank)
    return standings
