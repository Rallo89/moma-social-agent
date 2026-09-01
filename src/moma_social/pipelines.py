"""Le tre pipeline di contenuto.

Ognuna: legge i dati -> costruisce il contesto -> renderizza immagini e
caption -> restituisce un PostDraft. La pubblicazione e' un passo separato
(publish.py) cosi' che generare e pubblicare restino testabili in isolamento.
"""

from __future__ import annotations

import datetime as dt

from .captions import render_caption
from .config import Config
from .errors import NoDataError
from .models import PostDraft
from .render import post_size, render
from .repos import (
    events_by_day,
    fetch_events,
    fetch_leg_results,
    fetch_standings,
    formats_on,
    same_format,
)
from .timeutil import fmt_range, resolve_date, week_bounds


def _density(count: int) -> str:
    """Classe CSS che rimpicciolisce il corpo quando le righe sono troppe."""
    if count >= 12:
        return "dense-12"
    if count >= 10:
        return "dense-10"
    if count >= 8:
        return "dense-8"
    return ""


def _stamp(cfg: Config, kind: str, day: dt.date, suffix: str = "") -> str:
    tail = f"-{suffix}" if suffix else ""
    return f"{day.isoformat()}-{kind}{tail}"


def _background(cfg: Config, kind: str) -> str:
    return cfg.get(f"posts.{kind}.background", "") or ""


# ── 1. Calendario settimanale (lunedi 10:00) ────────────────────────────────
def weekly_calendar(cfg: Config, day: dt.date | None = None) -> PostDraft:
    day = day or resolve_date("today", cfg.timezone)
    start, end = week_bounds(day)
    events = fetch_events(cfg, start, end)
    days = events_by_day(events)
    formats = formats_on(events)
    periodo = fmt_range(start, end)

    image = render(
        cfg,
        cfg.require("posts.weekly_calendar.image_template"),
        {
            "days": days,
            "periodo": periodo,
            "events_count": len(events),
            "formats": formats,
            "background": _background(cfg, "weekly_calendar"),
            "density": _density(len(events) + len(days)),
        },
        _stamp(cfg, "calendario", start),
        size=post_size(cfg, "weekly_calendar"),
    )
    caption = render_caption(
        cfg, "weekly_calendar",
        {
            "days": days,
            "periodo": periodo,
            "events_count": len(events),
            "formats": formats,
            "signup_url": next((e.signup_url for e in events if e.signup_url), ""),
        },
        extra_hashtags=[f"#{f.replace(' ', '')}" for f in formats],
    )
    return PostDraft(
        kind="weekly_calendar",
        images=[str(image)],
        caption=caption,
        meta={"week_start": start.isoformat(), "week_end": end.isoformat(),
              "events": len(events), "formats": formats},
    )


# ── 2. Formato del giorno (mercoledi e giovedi 10:00) ───────────────────────
def format_spotlight(cfg: Config, day: dt.date | None = None,
                     fmt: str = "") -> PostDraft:
    day = day or resolve_date("today", cfg.timezone)
    try:
        events = fetch_events(cfg, day, day)
    except NoDataError:
        fallback = cfg.get(
            f"content.formats_by_weekday.{day.strftime('%A').lower()}", ""
        )
        if not fallback:
            raise
        # Nessun evento in sorgente ma un formato di riserva in config:
        # si pubblica comunque la card del formato, senza dettagli evento.
        events = []
        fmt = fmt or fallback

    if events:
        fmt = fmt or formats_on(events)[0]
        events = [e for e in events if not e.format or same_format(e.format, fmt)]
    main = events[0] if events else None

    facts = [
        ("Quando", (main.start_time if main and main.start_time else "") or "Vedi bio"),
        ("Dove", (main.venue if main else "") or cfg.get("org.name", "")),
        ("Iscrizione", (main.entry_fee if main else "") or "—"),
        ("Premi", (main.prize if main else "") or "—"),
    ]
    tagline = cfg.get(f"content.taglines.{fmt.lower()}", "")

    image = render(
        cfg,
        cfg.require("posts.format_spotlight.image_template"),
        {
            "day": day, "format": fmt, "events": events, "main": main,
            "facts": facts, "tagline": tagline,
            "cta": "Iscrizioni aperte" if main and main.signup_url else "",
            "background": _background(cfg, "format_spotlight"),
            "density": _density(len(events) * 2),
        },
        _stamp(cfg, "formato", day, fmt.lower().replace(" ", "-")),
        size=post_size(cfg, "format_spotlight"),
    )
    caption = render_caption(
        cfg, "format_spotlight",
        {"day": day, "format": fmt, "events": events, "main": main,
         "facts": facts, "tagline": tagline},
        extra_hashtags=[f"#{fmt.replace(' ', '')}"],
    )
    return PostDraft(
        kind="format_spotlight",
        images=[str(image)],
        caption=caption,
        meta={"day": day.isoformat(), "format": fmt, "events": len(events)},
    )


# ── 3. Risultati di tappa + classifica (giovedi e venerdi 03:00) ────────────
def leg_results(cfg: Config, day: dt.date | None = None, fmt: str = "") -> PostDraft:
    """Carosello a 2 slide sui risultati della tappa di `day` (default: ieri)."""
    day = day or resolve_date("yesterday", cfg.timezone)
    leg = fetch_leg_results(cfg, day, fmt)
    standings = fetch_standings(cfg, leg.format)

    top_n = cfg.get("posts.leg_results.top_n", 8)
    standings_top_n = cfg.get("posts.leg_results.standings_top_n", 10)
    rows = leg.rows[:top_n]
    standings_rows = standings.rows[:standings_top_n]

    templates = cfg.require("posts.leg_results.image_templates")
    background = _background(cfg, "leg_results")
    slide_results = render(
        cfg, templates[0],
        {"leg": leg, "rows": rows, "background": background, "density": _density(len(rows))},
        _stamp(cfg, "risultati", day, leg.format.lower().replace(" ", "-")),
        size=post_size(cfg, "leg_results"),
    )
    slide_standings = render(
        cfg, templates[1],
        {"standings": standings, "rows": standings_rows, "leg": leg,
         "background": _background(cfg, "leg_results_standings") or background,
         "density": _density(len(standings_rows))},
        _stamp(cfg, "classifica", day, leg.format.lower().replace(" ", "-")),
        size=post_size(cfg, "leg_results_standings"),
    )

    caption = render_caption(
        cfg, "leg_results",
        {"leg": leg, "rows": rows, "standings": standings,
         "standings_rows": standings_rows,
         "next_event_label": _next_event_label(cfg, day, leg.format)},
        extra_hashtags=[f"#{leg.format.replace(' ', '')}"],
    )
    return PostDraft(
        kind="leg_results",
        images=[str(slide_results), str(slide_standings)],
        caption=caption,
        meta={"day": day.isoformat(), "format": leg.format, "leg": leg.leg,
              "players": leg.players_count, "winner": leg.winner.player if leg.winner else ""},
    )


def _next_event_label(cfg: Config, after: dt.date, fmt: str) -> str:
    """Prossimo appuntamento dello stesso formato, per chiudere la caption."""
    try:
        upcoming = fetch_events(cfg, after + dt.timedelta(days=1),
                                after + dt.timedelta(days=28))
    except NoDataError:
        return "in arrivo, resta sintonizzato"
    for event in upcoming:
        if same_format(event.format, fmt):
            return f"{event.day_label}{' · ' + event.start_time if event.start_time else ''}"
    return "in arrivo, resta sintonizzato"


PIPELINES = {
    "weekly_calendar": weekly_calendar,
    "format_spotlight": format_spotlight,
    "leg_results": leg_results,
}
