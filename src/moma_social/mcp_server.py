"""Server MCP: espone i dati e le pipeline come tool per Claude Code.

Perche' un server MCP e non solo la CLI: cosi' Claude puo' *interrogare* i
dati (cosa si gioca questa settimana? chi guida la classifica Pioneer?) e
generare anteprime durante una conversazione, senza che l'operatore debba
ricordare la sintassi dei comandi. La pubblicazione resta un tool separato
e dichiarato, in modo che l'approvazione sia sempre esplicita.

Avvio:  python -m moma_social.mcp_server      (vedi .mcp.json)
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

# L'SDK MCP ha rinominato la classe passando dalla 1.x alla 2.x: stessa API
# (decoratori .tool()/.resource(), .run()), nome diverso.
try:
    from mcp.server import MCPServer as _Server
except ImportError:  # pragma: no cover - SDK 1.x
    from mcp.server.fastmcp import FastMCP as _Server

from . import config
from .errors import MtgSocialError
from .pipelines import PIPELINES, PIPELINES_MULTI, drafts
from .publish import ledger_path, publish_draft
from .repos import events_by_day, fetch_events, fetch_leg_results, fetch_standings
from .timeutil import fmt_range, resolve_date, week_bounds

mcp = _Server("moma-social", instructions=__doc__)


def _cfg():
    return config.load()


def _day(value: str | None) -> dt.date:
    cfg = _cfg()
    return resolve_date(value or "today", cfg.timezone)


@mcp.tool()
def agenda_settimana(data: str = "today") -> str:
    """Eventi della settimana che contiene `data` (today | yesterday | AAAA-MM-GG).

    Usalo per sapere cosa si gioca prima di scrivere o rivedere un post.
    """
    cfg = _cfg()
    start, end = week_bounds(_day(data))
    events = fetch_events(cfg, start, end)
    lines = [f"Settimana {fmt_range(start, end)} — {len(events)} eventi"]
    for day, group in events_by_day(events):
        lines.append(f"\n{day.isoformat()} ({group[0].weekday})")
        for event in group:
            lines.append(
                f"  · {event.start_time or '—'} {event.label} [{event.format}]"
                f"{' @' + event.venue if event.venue else ''}"
                f"{' — ' + event.notes if event.notes else ''}"
            )
    return "\n".join(lines)


@mcp.tool()
def risultati_tappa(data: str = "yesterday", formato: str = "") -> str:
    """Risultati della tappa giocata in `data`, opzionalmente filtrati per formato."""
    cfg = _cfg()
    leg = fetch_leg_results(cfg, _day(data), formato)
    lines = [
        f"{leg.format} — {leg.leg or 'tappa'} del {leg.date.isoformat()}"
        f" ({leg.players_count} giocatori{', ' + leg.venue if leg.venue else ''})"
    ]
    lines += [
        f"  {row.rank}. {row.player}"
        f"{' — ' + row.deck if row.deck else ''}"
        f"{'  ' + row.record if row.record else ''}"
        for row in leg.rows
    ]
    return "\n".join(lines)


@mcp.tool()
def classifica(formato: str, stagione: str = "") -> str:
    """Classifica generale aggiornata di un formato."""
    standings = fetch_standings(_cfg(), formato, stagione)
    lines = [f"Classifica {standings.format}"
             + (f" — stagione {standings.season}" if standings.season else "")]
    lines += [
        f"  {row.rank}. {row.player} — {row.points} pt"
        f"{' (' + str(row.events_played) + ' tappe)' if row.events_played else ''} {row.trend}"
        for row in standings.rows
    ]
    return "\n".join(lines)


@mcp.tool()
def genera_post(tipo: str, data: str = "", formato: str = "",
                id_torneo: str = "") -> str:
    """Genera immagini e caption di un post SENZA pubblicarlo.

    tipo: weekly_calendar | story_event | format_spotlight | leg_results
    Restituisce i path delle immagini e il testo, da rivedere prima di pubblicare.
    """
    tipi = {**PIPELINES, **PIPELINES_MULTI}
    if tipo not in tipi:
        return f"Tipo sconosciuto: {tipo}. Validi: {', '.join(tipi)}"
    if id_torneo and tipo != "story_event":
        return "id_torneo è disponibile solo per story_event"
    if id_torneo and (data or formato):
        return "id_torneo non si combina con data o formato"
    cfg = _cfg()
    kwargs = ({"tournament_id": id_torneo} if id_torneo else
              {} if tipo == "weekly_calendar" else {"fmt": formato})
    # Una serata con due tornei sono due post: si restituiscono entrambi.
    bozze = drafts(cfg, tipo, _day(data) if data else None, **kwargs)
    from .publish import save_draft_files
    return json.dumps(
        [{"tipo": draft.kind, "immagini": draft.images,
          "carosello": draft.is_carousel, "caption": draft.caption,
          "meta": draft.meta, "anteprima": str(save_draft_files(cfg, draft))}
         for draft in bozze],
        ensure_ascii=False, indent=2,
    )


@mcp.tool()
def pubblica_post(tipo: str, data: str = "", formato: str = "",
                  conferma: bool = False, id_torneo: str = "") -> str:
    """Genera e PUBBLICA su Instagram. Richiede conferma=true.

    Senza conferma esegue un dry-run: mostra cosa uscirebbe senza pubblicare.
    """
    tipi = {**PIPELINES, **PIPELINES_MULTI}
    if tipo not in tipi:
        return f"Tipo sconosciuto: {tipo}. Validi: {', '.join(tipi)}"
    if id_torneo and tipo != "story_event":
        return "id_torneo è disponibile solo per story_event"
    if id_torneo and (data or formato):
        return "id_torneo non si combina con data o formato"
    cfg = _cfg()
    kwargs = ({"tournament_id": id_torneo} if id_torneo else
              {} if tipo == "weekly_calendar" else {"fmt": formato})
    bozze = drafts(cfg, tipo, _day(data) if data else None, **kwargs)
    return json.dumps([publish_draft(cfg, draft, dry_run=not conferma)
                       for draft in bozze], ensure_ascii=False, indent=2)


@mcp.tool()
def storico_pubblicazioni(ultimi: int = 10) -> str:
    """Ultime pubblicazioni registrate nel ledger (per capire cosa e' gia' uscito)."""
    path = ledger_path(_cfg())
    if not path.exists():
        return "Nessuna pubblicazione registrata."
    entries = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    return "\n".join(entries[-ultimi:])


@mcp.tool()
def diagnostica() -> str:
    """Verifica configurazione, sorgenti dati, rendering e credenziali Instagram."""
    import contextlib
    import io

    from .cli import build_parser, cmd_doctor

    args = build_parser().parse_args(["doctor"])
    buffer = io.StringIO()
    with contextlib.redirect_stdout(buffer):
        try:
            cmd_doctor(args)
        except MtgSocialError as exc:
            buffer.write(f"\nErrore: {exc}")
    return buffer.getvalue()


@mcp.resource("momasocial://templates")
def templates_disponibili() -> str:
    """Elenco dei template immagine e caption presenti nel repo."""
    root = Path(config.project_root()) / "templates"
    images = sorted(p.name for p in (root / "images").glob("*.j2"))
    captions = sorted(p.name for p in (root / "captions").glob("*.j2"))
    return json.dumps({"immagini": images, "caption": captions}, indent=2)


def main() -> None:  # pragma: no cover
    mcp.run()


if __name__ == "__main__":  # pragma: no cover
    main()
