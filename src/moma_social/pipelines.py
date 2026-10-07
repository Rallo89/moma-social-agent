"""Le tre pipeline di contenuto.

Ognuna: legge i dati -> costruisce il contesto -> renderizza immagini e
caption -> restituisce un PostDraft. La pubblicazione e' un passo separato
(publish.py) cosi' che generare e pubblicare restino testabili in isolamento.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import warnings
from uuid import UUID

from .captions import render_caption
from .config import Config
from .errors import ConfigError, MtgSocialError, NoDataError, SourceError
from .models import (
    PostDraft,
    Standings,
    format_fee,
    meta_breakdown,
    stage_from_title,
)
from .render import post_size, render
from .repos import (
    events_by_day,
    fetch_event_by_id,
    fetch_events,
    fetch_leg_results,
    fetch_leg_results_all,
    fetch_standings_all,
    formats_on,
    same_format,
)
from .storyutil import story_jpeg
from .timeutil import (
    fmt_date,
    fmt_month,
    fmt_range,
    month_bounds,
    next_month,
    resolve_date,
    week_bounds,
    weekday_it,
)


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


def _pagine(righe: list, per_pagina: int) -> list[list]:
    """Spezza le righe in slide. Almeno una pagina, anche se vuota."""
    if per_pagina <= 0:
        return [righe]
    return [righe[i:i + per_pagina] for i in range(0, len(righe), per_pagina)] or [[]]


def _background(cfg: Config, kind: str) -> str:
    return cfg.get(f"posts.{kind}.background", "") or ""


# ── La card evento, condivisa dal calendario e dal formato del giorno ───────
def _testo_evento(cfg: Config, chiave: str, event, day: dt.date, fmt: str,
                  default: str = "") -> str:
    """Un campo della card, composto dal modello scritto in configurazione.

    I dati che il database non espone — ora, link iscrizioni, cadenza — vivono
    in config invece che nel codice: cambiarli non richiede una release.
    """
    modello = cfg.get(f"content.evento.{chiave}", default)
    if not modello:
        return ""
    return modello.format(
        format=fmt,
        formato=fmt,
        weekday=weekday_it(day),
        giorno=fmt_date(day, with_weekday=True),
        data=fmt_date(day),
        title=(event.title if event else ""),
        venue=(event.venue if event else ""),
        city=(event.city if event else "") or cfg.get("org.city", ""),
        fee=(event.entry_fee if event else ""),
        time=(event.start_time if event else ""),
        org=cfg.get("org.name", ""),
    ).strip()


def _per_formato(cfg: Config, chiave: str, fmt: str) -> str:
    """Un valore che cambia col formato, con un default per tutti gli altri.

    La quota del Pauper non e' quella del Limited: tenerla in una tabella
    evita di doverla scrivere evento per evento nel database.
    """
    return (cfg.get(f"content.evento.{chiave}.{fmt.lower()}", "")
            or cfg.get(f"content.evento.{chiave}.default", ""))


def _iscrizioni(cfg: Config, events: list) -> str:
    """Il link da mettere in caption.

    Se un evento porta il proprio link vince quello; altrimenti vale la pagina
    iscrizioni dell'associazione. Un post che dice "link in bio" quando il
    link esiste e' un'occasione persa a ogni pubblicazione.
    """
    proprio = next((e.signup_url for e in events if e.signup_url), "")
    return proprio or cfg.get("content.evento.link", "")


def _senza_schema(url: str) -> str:
    """L'indirizzo come lo vuole la grafica: senza https://, senza slash finale."""
    for prefisso in ("https://", "http://"):
        if url.startswith(prefisso):
            url = url[len(prefisso):]
    return url.rstrip("/")


def _titolo_evento(cfg: Config, event, day: dt.date, fmt: str) -> tuple[str, str]:
    """Sopratitolo e titolo della card: (lega, "Tappa N").

    Una tappa di lega si nomina sempre allo stesso modo, cosi' la grafica non
    cambia forma ogni settimana solo perche' e' cambiato il nome del torneo a
    database. Un evento spot, che non appartiene a nessuna lega, tiene invece
    il nome che ha: e' l'unica cosa che lo identifica.
    """
    if event and event.league:
        if event.is_final:
            return event.league, cfg.get("content.evento.titolo_finale", "Finale")
        if event.stage:
            modello = cfg.get("content.evento.titolo_tappa", "Tappa {stage}")
            return event.league, modello.format(stage=event.stage)
    if event and event.title:
        return "", event.title
    return "", _testo_evento(cfg, "titolo", event, day, fmt, "{weekday} {format}")


def _card_evento(cfg: Config, day: dt.date, fmt: str, event=None,
                 kicker_1: str = "", kicker_2: str = "") -> dict:
    """Contesto della grafica evento: gli slot del template del grafico."""
    quando = (f"{fmt_date(day, with_weekday=True)}, {event.start_time}"
              if event and event.start_time
              else _testo_evento(cfg, "quando", event, day, fmt,
                                 "{giorno}"))
    sede = _testo_evento(cfg, "dove", event, day, fmt)
    dove = (event.venue if event and event.venue else "") or sede
    # L'indirizzo e' quello scritto in configurazione, non quello a database:
    # li' e' una stringa di geocodifica lunga una riga e mezzo, buona per una
    # mappa e illeggibile su una locandina. Vale solo quando la sede coincide
    # con quella abituale, altrimenti indicherebbe il posto sbagliato.
    indirizzo = (_testo_evento(cfg, "indirizzo", event, day, fmt)
                 if dove.strip().casefold() == sede.strip().casefold() else "")
    # La quota del torneo vince sempre: quella in configurazione e' un ripiego
    # per gli eventi che a database non ce l'hanno.
    quota = (format_fee(event.entry_fee if event else "")
             or _per_formato(cfg, "quota", fmt))
    sopratitolo, titolo = _titolo_evento(cfg, event, day, fmt)
    return {
        "kicker_1": kicker_1 or _testo_evento(cfg, "kicker_1", event, day, fmt),
        "kicker_2": kicker_2 or _testo_evento(cfg, "kicker_2", event, day, fmt),
        "badge": _testo_evento(cfg, "badge", event, day, fmt, "{format}"),
        "sopratitolo": sopratitolo,
        "titolo": titolo,
        "voci": [
            {"etichetta": "Quando", "valore": quando, "dettaglio": ""},
            {"etichetta": "Dove", "valore": dove, "dettaglio": indirizzo},
            {"etichetta": "Iscrizione", "valore": quota, "dettaglio": ""},
        ],
        "link": _senza_schema(_testo_evento(cfg, "link", event, day, fmt)),
        "invito": cfg.get("content.evento.invito", "Iscriviti"),
    }


def _una_card_per_tappa(events: list) -> list:
    """Scarta i doppioni: una serata su piu' tavoli resta un evento solo.

    Le tappe di Limited girano su due o tre tavoli, e a database sono tornei
    distinti ("Tappa 3 - TAV. A", "- TAV. B"). Per chi legge il calendario
    sono la stessa serata: tre card identiche sarebbero solo rumore.
    """
    viste, unici = set(), []
    for evento in events:
        chiave = ((evento.date, evento.league, evento.stage, evento.is_final)
                  if evento.league else (evento.date, evento.title))
        if chiave in viste:
            continue
        viste.add(chiave)
        unici.append(evento)
    return unici


def _serata(cfg: Config, event) -> dict:
    """Una riga dell'elenco settimanale: quando, e cosa si gioca."""
    ora = event.start_time or cfg.get("content.evento.ora_default", "")
    quando = f"{weekday_it(event.date)} {event.date.day}"
    if ora:
        quando += f" · {ora}"
    if event.league:
        coda = ("Finale" if event.is_final
                else (f"Tappa {event.stage}" if event.stage else ""))
    else:
        # Uno spot non ha tappa da citare: vale il suo nome.
        coda = event.title
    # In un calendario si cerca il formato: c'e' sempre in testa, tranne
    # quando il nome dell'evento lo dice gia' ("Serata Commander").
    if not event.format:
        return {"quando": quando, "cosa": coda or event.label}
    if coda and event.format.casefold() in coda.casefold():
        return {"quando": quando, "cosa": coda}
    return {"quando": quando,
            "cosa": f"{event.format} · {coda}" if coda else event.format}


def _card_riepilogo(cfg: Config, events: list, inizio: dt.date, fine: dt.date,
                    periodo: str) -> dict:
    """Contesto della card che apre il carosello: la settimana in un colpo d'occhio."""
    return {
        "kicker_1": cfg.get("content.evento.kicker_calendario",
                            "Calendario settimanale"),
        "kicker_2": cfg.get("org.city", ""),
        "badge": periodo,
        "titolo": cfg.get("content.evento.titolo_settimana", "La settimana"),
        "serate": [_serata(cfg, evento) for evento in events],
        "link": _senza_schema(cfg.get("content.evento.link", "")),
        "invito": cfg.get("content.evento.invito", "Iscriviti"),
    }


def _gruppi_mensili(cfg: Config, events: list) -> list[dict]:
    """Sezioni alfabetiche per formato della didascalia Instagram."""
    icone = {
        "modern": "⚡", "pauper": "🃏", "limited": "🎁",
        "legacy": "⏳", "commander": "👑", "pioneer": "🧭",
        "premodern": "🔄", "standard": "⭐", "vintage": "🏆",
    }
    formati = sorted(formats_on(events), key=str.casefold)
    gruppi = []
    for formato in formati:
        tornei = sorted(
            (evento for evento in events if same_format(evento.format, formato)),
            key=lambda evento: (evento.date, evento.start_time or "99:99"),
        )
        gruppi.append({
            "formato": formato,
            "icona": icone.get(formato.casefold().strip(), "🎴"),
            "tornei": [{
                "data": f"{evento.date.day:02d}/{evento.date.month:02d}",
                "ora": evento.start_time or cfg.get("content.evento.ora_default", ""),
                "nome": evento.title or f"Torneo {formato}",
            } for evento in tornei],
        })
    senza_formato = sorted(
        (evento for evento in events if not evento.format),
        key=lambda evento: (evento.date, evento.start_time or "99:99"),
    )
    if senza_formato:
        gruppi.append({
            "formato": "Altri eventi", "icona": "🎴",
            "tornei": [{
                "data": f"{evento.date.day:02d}/{evento.date.month:02d}",
                "ora": evento.start_time or cfg.get("content.evento.ora_default", ""),
                "nome": evento.title or evento.label,
            } for evento in senza_formato],
        })
    return gruppi


def _giorni_mensili(cfg: Config, events: list) -> list[dict]:
    """Nella grafica, data e ora aprono una sezione con i tornei di quella sera."""
    sezioni: dict[tuple[dt.date, str], list] = {}
    for evento in sorted(events, key=lambda e: (e.date, e.start_time or "99:99")):
        ora = evento.start_time or cfg.get("content.evento.ora_default", "")
        sezioni.setdefault((evento.date, ora), []).append(evento)

    giorni = []
    for (data, ora), tornei in sezioni.items():
        righe = []
        for evento in tornei:
            nome = (evento.title or "").strip()
            if nome.casefold().startswith("torneo "):
                nome = nome[7:].strip()
            if not nome:
                nome = ("Finale" if evento.is_final else
                        f"Tappa {evento.stage}" if evento.stage else "Evento")
            righe.append({"formato": evento.format.upper(), "nome": nome})
        giorni.append({
            "quando": f"{fmt_date(data)} ore {ora.replace(':', '.')}",
            "tornei": righe,
        })
    return giorni


def _pagine_mensili(giorni: list[dict], righe_per_pagina: int) -> list[list[dict]]:
    """Impagina le date senza tagliare i tornei; ripete la data se serve."""
    limite = max(1, int(righe_per_pagina))
    pagine: list[list[dict]] = []
    pagina: list[dict] = []
    righe = 0

    def chiudi() -> None:
        nonlocal pagina, righe
        if pagina:
            pagine.append(pagina)
        pagina, righe = [], 0

    for giorno in giorni:
        rimanenti = giorno["tornei"]
        if pagina and (len(pagina) == 5 or righe + len(rimanenti) > limite):
            chiudi()
        while rimanenti:
            if righe == limite or len(pagina) == 5:
                chiudi()
            quanti = min(limite - righe, len(rimanenti))
            pagina.append({**giorno, "tornei": rimanenti[:quanti]})
            righe += quanti
            rimanenti = rimanenti[quanti:]
            if rimanenti:
                chiudi()
    chiudi()
    return pagine


# ── 1. Calendario settimanale (lunedi 10:00) ────────────────────────────────
def weekly_calendar(cfg: Config, day: dt.date | None = None) -> PostDraft:
    day = day or resolve_date("today", cfg.timezone)
    # Il post esce il sabato e annuncia la settimana che comincia: guarda
    # avanti di sette giorni invece di raccontare quella che sta finendo.
    if cfg.get("posts.weekly_calendar.settimana", "prossima") == "prossima":
        day = day + dt.timedelta(days=7)
    start, end = week_bounds(day)
    events = fetch_events(cfg, start, end)
    days = events_by_day(events)
    formats = formats_on(events)
    periodo = fmt_range(start, end)

    # Un evento per slide: e' la card che il grafico ha disegnato, e leggerla
    # sul feed e' piu' facile di una griglia con sette righe minuscole.
    template = cfg.require("posts.weekly_calendar.image_template")
    size = post_size(cfg, "weekly_calendar")
    kicker = cfg.get("content.evento.kicker_calendario", "Calendario settimanale")
    massimo = min(cfg.get("posts.weekly_calendar.max_carousel_slides", 10), 10)
    in_post = _una_card_per_tappa(events)
    # La card di riepilogo apre il carosello: prima si vede tutta la
    # settimana, poi si scorre per il dettaglio di ogni serata. Occupa una
    # slide, quindi le card evento che restano sono una in meno.
    riepilogo = cfg.get("posts.weekly_calendar.riepilogo", True)
    in_post = in_post[:massimo - 1 if riepilogo else massimo]
    immagini = []
    if riepilogo:
        immagini.append(render(
            cfg,
            cfg.get("posts.weekly_calendar.image_template_riepilogo",
                    "settimana.html.j2"),
            {**_card_riepilogo(cfg, in_post, start, end, periodo),
             "background": _background(cfg, "weekly_calendar"), "density": "",
             "tema": cfg.get("posts.weekly_calendar.tema", "arancione")},
            _stamp(cfg, "calendario", start, "00-riepilogo"),
            size=size,
        ))
    immagini += [
        render(
            cfg, template,
            {**_card_evento(cfg, evento.date, evento.format or "", evento,
                            kicker_1=kicker,
                            kicker_2=(f"{indice + 1}/{len(in_post)}"
                                      if len(in_post) > 1 else periodo)),
             "background": _background(cfg, "weekly_calendar"),
             "density": "", "tema": cfg.get("posts.weekly_calendar.tema", "arancione")},
            _stamp(cfg, "calendario", start,
                   f"{indice + 1:02d}-{(evento.format or 'evento').lower().replace(' ', '-')}"),
            size=size,
        )
        for indice, evento in enumerate(in_post)
    ]
    caption = render_caption(
        cfg, "weekly_calendar",
        {
            "days": days,
            "periodo": periodo,
            "events_count": len(events),
            "formats": formats,
            "signup_url": _iscrizioni(cfg, events),
        },
        extra_hashtags=[f"#{f.replace(' ', '')}" for f in formats],
    )
    return PostDraft(
        kind="weekly_calendar",
        images=[str(path) for path in immagini],
        caption=caption,
        meta={"week_start": start.isoformat(), "week_end": end.isoformat(),
              "events": len(events), "formats": formats,
              "slide": len(immagini),
              "slide_tagliate": len(_una_card_per_tappa(events)) - len(in_post)},
    )


# ── 1bis. Calendario del mese (il 30, per il mese dopo) ─────────────────────
def monthly_calendar(cfg: Config, day: dt.date | None = None) -> PostDraft:
    """Tutti gli appuntamenti del mese successivo, in elenco.

    Gira a fine mese e guarda avanti: chi lo legge deve potersi segnare le
    date prima che il mese cominci.
    """
    day = day or resolve_date("today", cfg.timezone)
    inizio, fine = month_bounds(next_month(day))
    events = _una_card_per_tappa(fetch_events(cfg, inizio, fine))
    mese = fmt_month(inizio)

    giorni = _giorni_mensili(cfg, events)
    tutte_le_pagine = _pagine_mensili(
        giorni, cfg.get("posts.monthly_calendar.rows_per_slide", 8))
    max_slide = max(1, min(cfg.get("posts.monthly_calendar.max_carousel_slides", 10), 10))
    pagine = tutte_le_pagine[:max_slide - 1]

    template = cfg.get("posts.monthly_calendar.image_template", "mensile_elenco.html.j2")
    copertina = cfg.get("posts.monthly_calendar.image_template_cover",
                        "mensile_copertina.html.j2")
    size = post_size(cfg, "monthly_calendar")
    comuni = {
        "mese": mese.split()[0],
        "link": _senza_schema(cfg.get("content.evento.link", "")),
        "invito": cfg.get("content.evento.invito", "Iscriviti"),
    }
    immagini = [render(
        cfg, copertina, comuni,
        _stamp(cfg, "mese", inizio, "00-copertina"), size=size,
    )]
    immagini += [
        render(
            cfg, template,
            {**comuni, "giorni": pagina,
             "pagina": indice + 1, "pagine": len(pagine)},
            _stamp(cfg, "mese", inizio, f"{indice + 1:02d}-elenco"),
            size=size,
        )
        for indice, pagina in enumerate(pagine)
    ]
    caption = render_caption(
        cfg, "monthly_calendar",
        {"gruppi": _gruppi_mensili(cfg, events),
         "mese": mese, "periodo": mese,
         "events_count": len(events), "formats": formats_on(events),
         "signup_url": cfg.get("content.evento.link", "")},
        extra_hashtags=[f"#{f.replace(' ', '')}" for f in formats_on(events)],
    )
    return PostDraft(
        kind="monthly_calendar",
        images=[str(path) for path in immagini],
        caption=caption,
        meta={"month_start": inizio.isoformat(), "month_end": fine.isoformat(),
              "events": len(events), "slide": len(immagini),
              "slide_tagliate": len(tutte_le_pagine) - len(pagine)},
    )


# ── 1ter. Aggiornamento classifiche (lunedi 10:00) ──────────────────────────
def standings_update(cfg: Config, day: dt.date | None = None) -> PostDraft:
    """Una slide per lega, con la top 8 di ciascuna.

    Le classifiche si muovono di poco in una serata: raccontarle una volta a
    settimana, tutte insieme, dice piu' che appiccicarle in coda a ogni post
    di risultati.
    """
    day = day or resolve_date("today", cfg.timezone)
    stati = cfg.get("posts.standings_update.stati", []) or []
    classifiche = fetch_standings_all(cfg, stati)

    top_n = cfg.get("posts.standings_update.top_n", 8)
    massimo = min(cfg.get("posts.standings_update.max_carousel_slides", 10), 10)
    in_post = classifiche[:massimo]

    template = cfg.get("posts.standings_update.image_template", "classifica.html.j2")
    size = post_size(cfg, "standings_update")
    kicker = cfg.get("content.standings_subtitle", "Classifica generale")
    immagini = [
        render(
            cfg, template,
            {"kicker_1": kicker,
             "kicker_2": (f"{indice + 1}/{len(in_post)}" if len(in_post) > 1
                          else fmt_date(day)),
             "badge": classifica.format,
             "sopratitolo": "",
             "titolo": classifica.season or cfg.get("content.standings_title",
                                                    "Classifica"),
             "righe": classifica.rows[:top_n] if top_n else classifica.rows,
             "tema": cfg.get("posts.standings_update.tema", "chiaro"),
             "link": _senza_schema(cfg.get("content.evento.link", "")),
             "invito": cfg.get("content.evento.invito", "Iscriviti"),
             "background": _background(cfg, "standings_update"), "density": ""},
            _stamp(cfg, "classifiche", day,
                   f"{indice + 1:02d}-{classifica.format.lower().replace(' ', '-')}"),
            size=size,
        )
        for indice, classifica in enumerate(in_post)
    ]

    caption = render_caption(
        cfg, "standings_update",
        {"day": day, "classifiche": in_post, "top_n": top_n},
        extra_hashtags=[f"#{c.format.replace(' ', '')}" for c in in_post],
    )
    return PostDraft(
        kind="standings_update",
        images=[str(path) for path in immagini],
        caption=caption,
        meta={"day": day.isoformat(), "leghe": len(in_post),
              "slide": len(immagini),
              "slide_tagliate": len(classifiche) - len(in_post)},
    )


# ── 2. Formato del giorno (mercoledi e giovedi 04:00) ───────────────────────
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
    return _post_formato(cfg, day, fmt, events)


def format_spotlight_batch(cfg: Config, day: dt.date | None = None,
                           fmt: str = "") -> list[PostDraft]:
    """Un post per ogni formato in programma quel giorno.

    Pauper e Premodern la stessa sera sono due serate distinte, con due quote
    e due orari: raccontarne una sola non e' una scelta editoriale, e' l'ordine
    in cui il database ha restituito le righe.

    Il taglio e' il formato e non il singolo torneo: due leghe dello stesso
    formato nella stessa sera restano un annuncio solo, come gia' fa il
    calendario settimanale coi tavoli multipli di un Limited.
    """
    day = day or resolve_date("today", cfg.timezone)
    # Con --format si chiede un formato preciso: e' un post solo, ed e' la
    # strada che prende anche il ripiego da configurazione quando la sorgente
    # non ha eventi.
    if fmt:
        return [format_spotlight(cfg, day, fmt)]
    try:
        events = fetch_events(cfg, day, day)
    except NoDataError:
        return [format_spotlight(cfg, day)]

    formati = formats_on(_una_card_per_tappa(events))
    if not formati:
        return [format_spotlight(cfg, day)]
    return [_post_formato(cfg, day, f,
                          [e for e in events if same_format(e.format, f)])
            for f in formati]


def _post_formato(cfg: Config, day: dt.date, fmt: str, events: list) -> PostDraft:
    main = events[0] if events else None

    facts = [
        ("Quando", (main.start_time if main and main.start_time else "") or "Vedi bio"),
        ("Dove", (main.venue if main else "") or cfg.get("org.name", "")),
        ("Iscrizione", format_fee(main.entry_fee if main else "") or "—"),
        ("Premi", (main.prize if main else "") or "—"),
    ]
    tagline = cfg.get(f"content.taglines.{fmt.lower()}", "")

    image = render(
        cfg,
        cfg.require("posts.format_spotlight.image_template"),
        {**_card_evento(cfg, day, fmt, main),
         # Serviti anche al vecchio layout generato dai colori brand, che
         # resta utilizzabile finche' non tutti i post hanno una card.
         "day": day, "format": fmt, "events": events, "main": main,
         "facts": facts, "tagline": tagline,
         "cta": "Iscrizioni aperte" if main and main.signup_url else "",
         "background": _background(cfg, "format_spotlight"),
         "density": _density(len(events) * 2)},
        _stamp(cfg, "formato", day, fmt.lower().replace(" ", "-")),
        size=post_size(cfg, "format_spotlight"),
    )
    caption = render_caption(
        cfg, "format_spotlight",
        {"day": day, "format": fmt, "events": events, "main": main,
         "facts": facts, "tagline": tagline,
         "signup_url": _iscrizioni(cfg, events)},
        extra_hashtags=[f"#{fmt.replace(' ', '')}"],
    )
    return PostDraft(
        kind="format_spotlight",
        images=[str(image)],
        caption=caption,
        meta={"day": day.isoformat(), "format": fmt, "events": len(events)},
    )


def _story_skip(cfg: Config, event, reason: str) -> None:
    """Lascia una traccia nell'artefatto del workflow, oltre al log."""
    directory = cfg.resolve_path(cfg.get("render.output_dir", "out"))
    if cfg.get("render.cartella_per_giorno", True):
        directory /= resolve_date("today", cfg.timezone).isoformat()
    directory.mkdir(parents=True, exist_ok=True)
    with (directory / "stories-skipped.jsonl").open("a", encoding="utf-8") as handle:
        handle.write(json.dumps({
            "day": event.date.isoformat(), "title": event.title,
            "tournament_id": event.tournament_id, "reason": reason,
        }, ensure_ascii=False) + "\n")


def _story_illustration(cfg: Config, fmt: str) -> dict:
    illustrations = cfg.section("posts.story_event.illustrations")
    key = fmt.strip().lower()
    return illustrations.get(key) or illustrations.get("default", {})


def story_events_batch(cfg: Config, day: dt.date | None = None,
                       fmt: str = "", tournament_id: str = "") -> list[PostDraft]:
    """Storie di oggi/domani, oppure una storia scelta per UUID completo."""
    if tournament_id and (day is not None or fmt):
        raise ConfigError("--tournament-id non si combina con --date o --format")
    today = resolve_date("today", cfg.timezone)
    if tournament_id:
        events = [fetch_event_by_id(cfg, tournament_id)]
    else:
        day = day or today
        events = fetch_events(cfg, day, day + dt.timedelta(days=1))
    stories = []
    skipped_invalid = []
    for event in events:
        if fmt and not same_format(event.format, fmt):
            continue
        if not event.tournament_id:
            reason = "ID del torneo mancante"
        else:
            try:
                UUID(event.tournament_id)
                reason = ""
            except ValueError:
                reason = "ID del torneo non valido"
        if reason:
            if tournament_id:
                raise SourceError(f"{reason}: {event.title}")
            skipped_invalid.append(f"{event.title} ({reason})")
            _story_skip(cfg, event, reason)
            warnings.warn(
                f"Storia saltata: {reason} "
                f"({event.date}, {event.title}, id={event.tournament_id or 'mancante'})",
                stacklevel=2,
            )
            continue
        if tournament_id:
            phase = ("oggi" if event.date == today else
                     "domani" if event.date == today + dt.timedelta(days=1) else
                     "evento")
        else:
            phase = "oggi" if event.date == day else "domani"
        date_label = fmt_date(event.date, with_weekday=True)
        time_label = event.start_time or cfg.get("content.evento.ora_default", "21:00")
        when = f"{date_label} · {time_label}"
        fee = format_fee(event.entry_fee) or _per_formato(cfg, "quota", event.format)
        size = post_size(cfg, "story_event")
        png = render(
            cfg, cfg.require("posts.story_event.image_template"),
            {"fase": phase, "formato": event.format, "titolo": event.title,
             "quando": when, "data": date_label,
             "data_breve": event.date.strftime("%d/%m/%Y"),
             "giorno": weekday_it(event.date), "ora": time_label,
             "dove": event.venue or cfg.get("content.evento.dove", ""),
             "quota": fee, "illustrazione": _story_illustration(cfg, event.format)},
            _stamp(cfg, "storia", event.date, f"{phase}-{event.tournament_id}"),
            size=size, scale=1,
        )
        image = story_jpeg(png, *size)
        stories.append(PostDraft(
            kind="story_event", images=[str(image)], caption="",
            meta={"day": event.date.isoformat(), "phase": phase,
                  "tournament_id": event.tournament_id, "format": event.format,
                  "title": event.title},
        ))
    if not stories:
        if skipped_invalid:
            raise SourceError(
                "Nessuna storia generata: tutti i tornei selezionati hanno un ID "
                "mancante o non valido: " + "; ".join(skipped_invalid)
            )
        raise NoDataError(f"Nessuna storia pubblicabile per {day} e {day + dt.timedelta(days=1)}")
    return stories


# ── Il meta della tappa, a spicchi ──────────────────────────────────────────
# Palette categorica validata sul fondo scuro della card (#14171a): banda di
# luminosita', soglia di croma, separazione per daltonismo e contrasto passano
# tutti. L'ordine e' fisso e non si cicla — un nono archetipo non genera un
# colore nuovo, entra in "Altri". Grigio per "Non dichiarato", che non e' un
# archetipo e non deve sembrarlo.
COLORI_META = ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300"]
# "Altri" e "Non dichiarato" non sono archetipi: due grigi, cosi' non
# competono con le fette che un archetipo ce l'hanno.
GRIGI_META = {"Altri": "#8a8f98", "Non dichiarato": "#4b5158"}


def _spicchi(fette: list[dict], raggio: float = 190, centro: float = 200,
             grigi: dict | None = None) -> list[dict]:
    """Trasforma le quote in archi SVG, in senso orario da mezzogiorno."""
    import math

    spicchi, angolo = [], -math.pi / 2
    for indice, fetta in enumerate(fette):
        colore = (grigi or GRIGI_META).get(fetta["nome"],
                                COLORI_META[indice % len(COLORI_META)])
        fine = angolo + 2 * math.pi * fetta["quota"]
        if fetta["quota"] >= 0.999:
            # Un cerchio intero non si disegna con un arco: gli estremi
            # coinciderebbero e il path resterebbe vuoto.
            percorso = (f"M {centro} {centro - raggio} "
                        f"A {raggio} {raggio} 0 1 1 {centro - 0.01} {centro - raggio} Z")
        else:
            x0, y0 = centro + raggio * math.cos(angolo), centro + raggio * math.sin(angolo)
            x1, y1 = centro + raggio * math.cos(fine), centro + raggio * math.sin(fine)
            grande = 1 if fetta["quota"] > 0.5 else 0
            percorso = (f"M {centro} {centro} L {x0:.2f} {y0:.2f} "
                        f"A {raggio} {raggio} 0 {grande} 1 {x1:.2f} {y1:.2f} Z")
        spicchi.append({**fetta, "colore": colore, "percorso": percorso})
        angolo = fine
    return spicchi


def _card_meta(cfg: Config, leg, kicker: str, suffisso: str) -> dict | None:
    """Contesto della slide sul meta. None se non c'e' niente da mostrare."""
    fette = meta_breakdown(
        leg.rows,
        massimo=cfg.get("posts.leg_results.meta_top_n", 5),
        altri=cfg.get("content.meta_altri", "Altri"),
        ignoto=cfg.get("content.meta_ignoto", "Non dichiarato"),
    )
    ignoto = cfg.get("content.meta_ignoto", "Non dichiarato")
    dichiarati = [f for f in fette if f["nome"] != ignoto]
    # Una torta di un colore solo con scritto "non dichiarato" non e' un grafico
    # del meta: e' il promemoria che i mazzi non sono stati registrati.
    if not dichiarati:
        return None
    return {
        "kicker_1": kicker, "kicker_2": suffisso,
        "badge": leg.format, "sopratitolo": "",
        "titolo": cfg.get("content.meta_titolo", "Il meta"),
        "spicchi": _spicchi(fette, grigi={
            cfg.get("content.meta_altri", "Altri"): GRIGI_META["Altri"],
            ignoto: GRIGI_META["Non dichiarato"],
        }),
        "link": _senza_schema(cfg.get("content.evento.link", "")),
        "invito": cfg.get("content.evento.invito", "Iscriviti"),
        "background": _background(cfg, "leg_results_meta"), "density": "",
    }


# ── 3. Risultati di tappa + meta della serata (giovedi e venerdi 03:00) ──────
def leg_results(cfg: Config, day: dt.date | None = None, fmt: str = "",
                senza_meta: bool = False) -> PostDraft:
    """Carosello sulla prima tappa di `day` (default: ieri).

    Quando la serata ha ospitato piu' tornei servono piu' post: li produce
    tutti `leg_results_batch`.
    """
    day = day or resolve_date("yesterday", cfg.timezone)
    return _post_di_tappa(cfg, day, fetch_leg_results(cfg, day, fmt), senza_meta)


def leg_results_batch(cfg: Config, day: dt.date | None = None, fmt: str = "",
                      senza_meta: bool = False) -> list[PostDraft]:
    """Un post per ogni torneo giocato quel giorno.

    Pauper e Premodern nella stessa serata sono due gare distinte, con due
    vincitori: meritano due post, non uno che li fonde.
    """
    day = day or resolve_date("yesterday", cfg.timezone)
    return [_post_di_tappa(cfg, day, leg, senza_meta)
            for leg in fetch_leg_results_all(cfg, day, fmt)]


def _post_di_tappa(cfg: Config, day: dt.date, leg, senza_meta: bool) -> PostDraft:
    """Carosello di una tappa: i risultati, poi il meta della serata.

    La classifica di lega non sta qui: si aggiorna una volta a settimana, in
    un post suo, mentre questo racconta la serata appena finita.
    """
    # Le bozze della serata vengono renderizzate prima di pubblicarne una.
    # Formato e data da soli farebbero sovrascrivere le slide di due tornei
    # dello stesso formato. Nome e lega identificano gli stessi gruppi usati
    # dal repository; il digest mantiene corto e stabile il nome del file.
    identita = json.dumps([leg.format, leg.leg, leg.league], ensure_ascii=False)
    suffisso = hashlib.sha256(identita.encode("utf-8")).hexdigest()[:12]
    nome_tappa = f"{leg.format.lower().replace(' ', '-')}-{suffisso}"

    # top_n = 0 significa "tutti": con piu' partecipanti di quanti ne stiano in
    # una slide il post diventa un carosello, non un elenco troncato in silenzio.
    top_n = cfg.get("posts.leg_results.top_n", 0)
    rows = leg.rows[:top_n] if top_n else leg.rows

    per_slide = cfg.get("posts.leg_results.rows_per_slide", 16)
    # La Graph API accetta al massimo 10 elementi per carosello (l'app ne
    # permette 20, ma noi pubblichiamo via API).
    max_slide = min(cfg.get("posts.leg_results.max_carousel_slides", 10), 10)

    templates = cfg.require("posts.leg_results.image_templates")
    background = _background(cfg, "leg_results")
    torneo = cfg.get("content.tournament_name", "Torneo {format}").format(
        format=leg.format
    )
    hashtag = cfg.get("content.hashtag_grafica", "")
    kicker = cfg.get("content.leg_kicker", "Risultati di tappa")

    # "Modern Fall tappa 1" diventa "Tappa 1": lo stesso titolo standard delle
    # card del calendario, cosi' i due post si riconoscono come la stessa cosa.
    numero, finale = stage_from_title(leg.leg)
    if finale:
        titolo_tappa = cfg.get("content.evento.titolo_finale", "Finale")
    elif numero:
        titolo_tappa = cfg.get("content.evento.titolo_tappa",
                               "Tappa {stage}").format(stage=numero)
    else:
        titolo_tappa = leg.leg or leg.format

    # Il meta occupa una slide, quindi i risultati ne hanno una in meno.
    meta = None if senza_meta else _card_meta(cfg, leg, kicker, fmt_date(day))
    pagine_tappa = _pagine(rows, per_slide)
    disponibili = max_slide - (1 if meta else 0)
    tagliate = max(0, len(pagine_tappa) - disponibili)
    pagine_tappa = pagine_tappa[:disponibili]

    def _slide(pagina, indice, totale):
        # Il numero di pagina compare solo quando ce n'e' piu' di una.
        suffisso = f"{indice + 1}/{totale}" if totale > 1 else fmt_date(day)
        nome = _stamp(cfg, "risultati", day, nome_tappa)
        return render(
            cfg, templates[0],
            {# La cornice comune: gli stessi slot delle card del calendario.
             "kicker_1": kicker, "kicker_2": suffisso,
             "badge": leg.format, "sopratitolo": "", "titolo": titolo_tappa,
             "righe": pagina,
             "link": _senza_schema(cfg.get("content.evento.link", "")),
             "invito": cfg.get("content.evento.invito", "Iscriviti"),
             # Serviti al vecchio template su sfondo Canva, ancora disponibile.
             "leg": leg, "standings": Standings(format=leg.format),
             "title": torneo, "hashtag": hashtag, "rows": pagina,
             "row_style": cfg.get("posts.leg_results.row_style", "strip"),
             "subtitle": (titolo_tappa
                          + (f" · {indice + 1}/{totale}" if totale > 1 else "")),
             "background": _background(cfg, "leg_results") or background,
             "density": _density(len(pagina))},
            f"{nome}-{indice + 1}" if totale > 1 else nome,
            size=post_size(cfg, "leg_results"),
        )

    immagini = [_slide(pagina, i, len(pagine_tappa))
                for i, pagina in enumerate(pagine_tappa)]
    if meta:
        immagini.append(render(
            cfg,
            cfg.get("posts.leg_results.image_template_meta", "meta.html.j2"),
            meta,
            _stamp(cfg, "meta", day, nome_tappa),
            size=post_size(cfg, "leg_results"),
        ))

    caption = render_caption(
        cfg, "leg_results",
        {"leg": leg, "rows": rows, "meta": (meta or {}).get("spicchi", []),
         "next_event_label": _next_event_label(cfg, day, leg.format)},
        extra_hashtags=[f"#{leg.format.replace(' ', '')}"],
    )
    return PostDraft(
        kind="leg_results",
        images=[str(path) for path in immagini],
        caption=caption,
        meta={"day": day.isoformat(), "format": leg.format, "leg": leg.leg,
              "players": leg.players_count,
              "winner": leg.winner.player if leg.winner else "",
              "slide": len(immagini), "slide_tappa": len(pagine_tappa),
              "slide_meta": 1 if meta else 0,
              "slide_tagliate": tagliate},
    )


def _next_event_label(cfg: Config, after: dt.date, fmt: str) -> str:
    """Prossimo appuntamento dello stesso formato, per chiudere la caption.

    E' una rifinitura, non un requisito: qualunque problema nel recuperarla —
    sorgente irraggiungibile compresa — deve degradare in una frase generica,
    non far fallire un post che ha gia' tutti i dati che gli servono.
    """
    try:
        upcoming = fetch_events(cfg, after + dt.timedelta(days=1),
                                after + dt.timedelta(days=28))
    except MtgSocialError:
        return "in arrivo, resta sintonizzato"
    for event in upcoming:
        if same_format(event.format, fmt):
            return f"{event.day_label}{' · ' + event.start_time if event.start_time else ''}"
    return "in arrivo, resta sintonizzato"


PIPELINES = {
    "weekly_calendar": weekly_calendar,
    "monthly_calendar": monthly_calendar,
    "standings_update": standings_update,
    "format_spotlight": format_spotlight,
    "leg_results": leg_results,
}

# Alcune giornate valgono piu' di un post: qui le pipeline che lo sanno fare.
PIPELINES_MULTI = {
    "leg_results": leg_results_batch,
    "format_spotlight": format_spotlight_batch,
    "story_event": story_events_batch,
}


def drafts(cfg: Config, kind: str, day: dt.date | None = None,
           **kwargs) -> list[PostDraft]:
    """Tutte le bozze che quel giorno richiede per quel tipo di post."""
    if kind in PIPELINES_MULTI:
        return PIPELINES_MULTI[kind](cfg, day, **kwargs)
    return [PIPELINES[kind](cfg, day, **kwargs)]
