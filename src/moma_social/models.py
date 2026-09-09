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
    address: str = ""
    city: str = ""
    entry_fee: str = ""
    prize: str = ""
    signup_url: str = ""
    notes: str = ""
    # Lega di appartenenza e numero di tappa: insieme danno alla grafica un
    # titolo uguale ogni settimana ("Lega Modern Fall" / "Tappa 3") invece del
    # nome che il torneo ha a database, diverso ogni volta.
    league: str = ""
    stage: str = ""
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


def format_record(wins, losses, draws) -> str:
    """Comporre il record e' presentazione, non dato: sta qui, non nel database.

    I pareggi compaiono solo se ci sono: "3-0-1" quando c'e' un pari, "3-0"
    quando non ce n'e', invece di un "3-0-0" che nessuno scrive.
    """
    def numero(valore):
        try:
            return int(float(str(valore).strip()))
        except (TypeError, ValueError):
            return None

    v, s, p = numero(wins), numero(losses), numero(draws)
    if v is None or s is None:
        return ""
    return f"{v}-{s}-{p}" if p else f"{v}-{s}"


def format_fee(valore) -> str:
    """La quota come si scrive su una locandina, da come sta a database.

    Un database registra un numero: 7, 7.00, 7.5. Una grafica scrive "7 €" e
    "7,50 €". La conversione e' presentazione, quindi sta qui — e un valore
    gia' scritto per esteso ("Gratis", "10 € + buste") passa intatto, perche'
    chi l'ha scritto cosi' aveva una ragione.
    """
    testo = str(valore or "").strip()
    if not testo:
        return ""
    try:
        numero = float(testo.replace(",", "."))
    except ValueError:
        return testo
    if numero == int(numero):
        return f"{int(numero)} €"
    return f"{numero:.2f}".replace(".", ",") + " €"


@dataclass
class ResultRow:
    rank: int
    player: str
    deck: str = ""
    record: str = ""
    points: float | int | str = ""
    wins: int | str = ""
    losses: int | str = ""
    draws: int | str = ""
    extra: dict = field(default_factory=dict)


@dataclass
class LegResults:
    """Risultati di una singola tappa."""

    date: dt.date
    format: str
    leg: str = ""
    venue: str = ""
    players_count: int | str = ""
    # La lega di appartenenza: identifica quale classifica aggiornare quando
    # piu' leghe condividono lo stesso formato (tipicamente una per stagione).
    league: str = ""
    rows: list[ResultRow] = field(default_factory=list)

    @property
    def winner(self) -> ResultRow | None:
        """Primo classificato secondo l'ordine della tappa."""
        return self.rows[0] if self.rows else None

    @property
    def winners(self) -> list[ResultRow]:
        """Chi ha chiuso a pari punti in testa.

        La posizione da sola non basta: due giocatori possono finire a pari
        punteggio e venire separati solo dai tiebreaker. Dichiararne uno solo
        vincitore sarebbe scorretto verso l'altro.
        """
        if not self.rows:
            return []

        def punteggio(riga):
            try:
                return float(str(riga.points).strip())
            except (TypeError, ValueError):
                return None

        massimo = punteggio(self.rows[0])
        if massimo is None:
            return [self.rows[0]]
        return [r for r in self.rows if punteggio(r) == massimo]

    @property
    def ex_aequo(self) -> bool:
        return len(self.winners) > 1

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
    league: str = ""
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
