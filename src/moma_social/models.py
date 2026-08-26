"""Modello dati interno.

I nomi dei campi qui sono il *contratto*: qualunque sorgente (JSON, CSV,
Google Sheets, SQL) viene tradotta in queste strutture tramite la sezione
`map` della config. I template parlano solo questo linguaggio.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field

from .timeutil import fmt_date, weekday_it


@dataclass
class Event:
    date: dt.date
    title: str = ""
    format: str = ""
    start_time: str = ""
    venue: str = ""
    city: str = ""
    entry_fee: str = ""
    prize: str = ""
    signup_url: str = ""
    notes: str = ""
    extra: dict = field(default_factory=dict)

    @property
    def weekday(self) -> str:
        return weekday_it(self.date)

    @property
    def day_label(self) -> str:
        return fmt_date(self.date, with_weekday=True)

    @property
    def label(self) -> str:
        """Titolo da mostrare: il titolo esplicito, altrimenti il formato."""
        return self.title or self.format or "Evento"


@dataclass
class ResultRow:
    rank: int
    player: str
    deck: str = ""
    record: str = ""
    points: float | int | str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class LegResults:
    """Risultati di una singola tappa."""

    date: dt.date
    format: str
    leg: str = ""
    venue: str = ""
    players_count: int | str = ""
    rows: list[ResultRow] = field(default_factory=list)

    @property
    def winner(self) -> ResultRow | None:
        return self.rows[0] if self.rows else None

    @property
    def day_label(self) -> str:
        return fmt_date(self.date, with_weekday=True)


@dataclass
class StandingRow:
    rank: int
    player: str
    points: float | int | str = ""
    events_played: int | str = ""
    delta: int | str = ""
    extra: dict = field(default_factory=dict)

    @property
    def trend(self) -> str:
        """Freccia di tendenza rispetto alla tappa precedente."""
        try:
            value = int(self.delta)
        except (TypeError, ValueError):
            return ""
        if value > 0:
            return "▲"
        if value < 0:
            return "▼"
        return "="


@dataclass
class Standings:
    format: str
    season: str = ""
    rows: list[StandingRow] = field(default_factory=list)


@dataclass
class PostDraft:
    """Un post pronto: immagini in ordine di carosello + caption."""

    kind: str
    images: list[str]
    caption: str
    meta: dict = field(default_factory=dict)

    @property
    def is_carousel(self) -> bool:
        return len(self.images) > 1
