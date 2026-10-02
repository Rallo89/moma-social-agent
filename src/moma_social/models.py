"""Modello dati interno.

I nomi dei campi qui sono il *contratto*: qualunque sorgente (JSON, CSV,
Google Sheets, SQL) viene tradotta in queste strutture tramite la sezione
`map` della config. I template parlano solo questo linguaggio.
"""

from __future__ import annotations

import datetime as dt
import re
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
    is_final: bool = False
    extra: dict = field(default_factory=dict)
    tournament_id: str = ""

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


# Numeri di tappa scritti a parole: capitano, e sono pochi.
_ORDINALI = {
    "prima": 1, "seconda": 2, "terza": 3, "quarta": 4, "quinta": 5,
    "sesta": 6, "settima": 7, "ottava": 8, "nona": 9, "decima": 10,
}
# "Tappa 3", "3° tappa", "terza tappa" — tutte forme che compaiono davvero.
# Il numero e' di una o due cifre: cosi' l'anno in "Lega Pauper Fall 1° tappa
# 2026" non viene scambiato per la tappa 2026, ne' il 2023 di "Limited Winter
# 2023 Tappa 1" per la tappa 23.
_TAPPA_DOPO = re.compile(r"\btappa\s*n?[.°º]?\s*(\d{1,2})\b", re.IGNORECASE)
# Il segno di ordinale qui e' obbligatorio: e' l'unica cosa che distingue
# "1° tappa" da "Spring '26 tappa 8", dove il numero davanti e' l'anno.
_TAPPA_PRIMA = re.compile(r"\b(\d{1,2})\s*[°ºaª]\s*tappa\b", re.IGNORECASE)
_TAPPA_PAROLA = re.compile(r"\b(" + "|".join(_ORDINALI) + r")\s+tappa\b",
                           re.IGNORECASE)
_FINALE = re.compile(r"\bfinal[ei]\b", re.IGNORECASE)


def stage_from_title(titolo: str) -> tuple[str, bool]:
    """Numero di tappa e "e' una finale", letti dal nome del torneo.

    Il numero di tappa non e' una colonna del database: l'unico posto dove
    esiste e' il nome, scritto a mano e quindi in dieci modi diversi
    ("Tappa 3", "3° tappa", "quinta tappa", "Tappa 1 -Recupero"). Contarle in
    ordine di data non funziona: le finali sono datate fuori sequenza, una
    serata puo' avere piu' tavoli, e le tappe saltate lascerebbero un buco.

    Restituisce ("", False) quando non riconosce niente: meglio ricadere sul
    nome del torneo che stampare un numero sbagliato.
    """
    testo = str(titolo or "")
    if _FINALE.search(testo):
        return "", True
    for espressione in (_TAPPA_PRIMA, _TAPPA_DOPO):
        trovato = espressione.search(testo)
        if trovato:
            return trovato.group(1), False
    trovato = _TAPPA_PAROLA.search(testo)
    if trovato:
        return str(_ORDINALI[trovato.group(1).lower()]), False
    return "", False


def meta_breakdown(rows, massimo: int = 5, altri: str = "Altri",
                   ignoto: str = "Non dichiarato") -> list[dict]:
    """Quote degli archetipi giocati in una tappa, dal piu' diffuso.

    Oltre i primi `massimo` si accorpa in "Altri": una torta con quindici
    spicchi non si legge, e i colori distinguibili non sono infiniti. Chi non
    ha dichiarato il mazzo finisce in una fetta sua, sempre in fondo, perche'
    "non lo sappiamo" non e' un archetipo.
    """
    conteggio: dict[str, int] = {}
    for riga in rows:
        nome = (getattr(riga, "deck", "") or "").strip() or ignoto
        conteggio[nome] = conteggio.get(nome, 0) + 1
    if not conteggio:
        return []

    senza = conteggio.pop(ignoto, 0)
    ordinati = sorted(conteggio.items(), key=lambda v: (-v[1], v[0]))
    testa, coda = ordinati[:massimo], ordinati[massimo:]
    if coda:
        testa.append((altri, sum(n for _, n in coda)))
    if senza:
        testa.append((ignoto, senza))

    totale = sum(n for _, n in testa)
    return [{"nome": nome, "conta": n, "quota": n / totale,
             "percento": round(n * 100 / totale)}
            for nome, n in testa]


def event_label(event, tappa: str = "Tappa {stage}", finale: str = "Finale") -> str:
    """Come l'evento si chiama nei testi: "Modern Fall 2026 · Tappa 2".

    Lo stesso nome che compare sulla grafica, su una riga sola. Grafica e
    caption che chiamano lo stesso torneo in due modi diversi sembrano parlare
    di due serate diverse.
    """
    if event.league:
        if event.is_final:
            return f"{event.league} · {finale}"
        if event.stage:
            return f"{event.league} · {tappa.format(stage=event.stage)}"
    return event.title or event.format or "Evento"


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

        # Il massimo si cerca fra TUTTE le righe, non si assume che sia la
        # prima: quando posizione e punteggio non concordano — succede se un
        # iscritto non ha giocato ma una posizione gli e' stata assegnata
        # comunque — fidarsi della riga in testa fa incoronare chi ha zero.
        punteggiati = [(r, punteggio(r)) for r in self.rows]
        validi = [(r, p) for r, p in punteggiati if p is not None]
        massimo = max((p for _, p in validi), default=None)
        # Tutti a zero significa che questo torneo i punti non li registra:
        # allora l'unica cosa di cui fidarsi e' la posizione.
        if massimo is None or massimo <= 0:
            return [self.rows[0]]
        return [r for r, p in validi if p == massimo]

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
    # Stato della lega a database: serve a non pubblicare le stagioni chiuse.
    status: str = ""
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
