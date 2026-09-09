"""Le tre pipeline di contenuto.

Ognuna: legge i dati -> costruisce il contesto -> renderizza immagini e
caption -> restituisce un PostDraft. La pubblicazione e' un passo separato
(publish.py) cosi' che generare e pubblicare restino testabili in isolamento.
"""

from __future__ import annotations

import datetime as dt

from .captions import render_caption
from .config import Config
from .errors import MtgSocialError, NoDataError
from .models import PostDraft, Standings, format_fee, stage_from_title
from .render import post_size, render
from .repos import (
    events_by_day,
    fetch_events,
    fetch_leg_results,
    fetch_leg_results_all,
    fetch_standings,
    formats_on,
    same_format,
)
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
        "qr_image": cfg.get("content.evento.qr", ""),
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
        "qr_image": cfg.get("content.evento.qr", ""),
    }


# ── 1. Calendario settimanale (lunedi 10:00) ────────────────────────────────
def weekly_calendar(cfg: Config, day: dt.date | None = None) -> PostDraft:
    day = day or resolve_date("today", cfg.timezone)
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
             "background": _background(cfg, "weekly_calendar"), "density": ""},
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
             "density": ""},
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
            "signup_url": next((e.signup_url for e in events if e.signup_url), ""),
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

    # Un mese ha piu' serate di quante ne stiano leggibili in una slide: si
    # impagina invece di rimpicciolire il testo finche' non si legge piu'.
    per_slide = cfg.get("posts.monthly_calendar.rows_per_slide", 8)
    max_slide = min(cfg.get("posts.monthly_calendar.max_carousel_slides", 10), 10)
    pagine = _pagine(events, per_slide)[:max_slide]

    template = cfg.get("posts.monthly_calendar.image_template", "settimana.html.j2")
    size = post_size(cfg, "monthly_calendar")
    immagini = [
        render(
            cfg, template,
            {"kicker_1": cfg.get("content.evento.kicker_mensile",
                                 "Calendario del mese"),
             "kicker_2": (f"{indice + 1}/{len(pagine)}" if len(pagine) > 1
                          else cfg.get("org.city", "")),
             "badge": mese,
             "titolo": cfg.get("content.evento.titolo_mese", "Il mese"),
             "serate": [_serata(cfg, evento) for evento in pagina],
             "link": _senza_schema(cfg.get("content.evento.link", "")),
             "invito": cfg.get("content.evento.invito", "Iscriviti"),
             "qr_image": cfg.get("content.evento.qr", ""),
             "background": _background(cfg, "monthly_calendar"), "density": ""},
            _stamp(cfg, "mese", inizio,
                   f"{indice + 1:02d}" if len(pagine) > 1 else ""),
            size=size,
        )
        for indice, pagina in enumerate(pagine)
    ]
    caption = render_caption(
        cfg, "monthly_calendar",
        {"days": events_by_day(events), "mese": mese, "periodo": mese,
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
              "slide_tagliate": max(0, len(_pagine(events, per_slide)) - len(pagine))},
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
def leg_results(cfg: Config, day: dt.date | None = None, fmt: str = "",
                senza_classifica: bool = False) -> PostDraft:
    """Carosello sulla prima tappa di `day` (default: ieri).

    Quando la serata ha ospitato piu' tornei servono piu' post: li produce
    tutti `leg_results_batch`.
    """
    day = day or resolve_date("yesterday", cfg.timezone)
    return _post_di_tappa(cfg, day, fetch_leg_results(cfg, day, fmt),
                          senza_classifica)


def leg_results_batch(cfg: Config, day: dt.date | None = None, fmt: str = "",
                      senza_classifica: bool = False) -> list[PostDraft]:
    """Un post per ogni torneo giocato quel giorno.

    Pauper e Premodern nella stessa serata sono due gare distinte, con due
    vincitori e due classifiche: meritano due post, non uno che li fonde.
    """
    day = day or resolve_date("yesterday", cfg.timezone)
    return [_post_di_tappa(cfg, day, leg, senza_classifica)
            for leg in fetch_leg_results_all(cfg, day, fmt)]


def _post_di_tappa(cfg: Config, day: dt.date, leg, senza_classifica: bool) -> PostDraft:
    """Carosello risultati + classifica generale di una singola tappa.

    La classifica generale e' facoltativa: se manca — formato senza lega,
    sorgente non ancora collegata, o `senza_classifica` — il post esce con le
    sole slide dei risultati invece di non uscire affatto.
    """
    if senza_classifica:
        standings = Standings(format=leg.format)
    elif not leg.league:
        # Torneo non collegato a nessuna lega: non esiste "la" classifica da
        # accostargli. Meglio il solo post dei risultati che una classifica
        # scelta a caso fra quelle dello stesso formato.
        standings = Standings(format=leg.format)
    else:
        try:
            standings = fetch_standings(cfg, leg.format, league=leg.league)
        except NoDataError:
            standings = Standings(format=leg.format)

    # top_n = 0 significa "tutti": con piu' partecipanti di quanti ne stiano in
    # una slide il post diventa un carosello, non un elenco troncato in silenzio.
    top_n = cfg.get("posts.leg_results.top_n", 0)
    standings_top_n = cfg.get("posts.leg_results.standings_top_n", 16)
    rows = leg.rows[:top_n] if top_n else leg.rows
    standings_rows = standings.rows[:standings_top_n] if standings_top_n else standings.rows

    per_slide = cfg.get("posts.leg_results.rows_per_slide", 16)
    # La Graph API accetta al massimo 10 elementi per carosello (l'app ne
    # permette 20, ma noi pubblichiamo via API).
    max_slide = min(cfg.get("posts.leg_results.max_carousel_slides", 10), 10)

    pagine_tappa = _pagine(rows, per_slide)
    pagine_classifica = _pagine(standings_rows, per_slide) if standings_rows else []
    tagliate = 0
    if len(pagine_tappa) + len(pagine_classifica) > max_slide:
        # I risultati sono la notizia: la classifica cede spazio per prima.
        spazio_classifica = max(1, max_slide - len(pagine_tappa)) if pagine_classifica else 0
        tagliate = len(pagine_classifica) - spazio_classifica
        pagine_classifica = pagine_classifica[:spazio_classifica]
        if len(pagine_tappa) + len(pagine_classifica) > max_slide:
            tagliate += len(pagine_tappa) - (max_slide - len(pagine_classifica))
            pagine_tappa = pagine_tappa[:max_slide - len(pagine_classifica)]

    templates = cfg.require("posts.leg_results.image_templates")
    background = _background(cfg, "leg_results")
    # Il nome del torneo compare nel titolo della grafica: "Torneo Pauper".
    torneo = cfg.get("content.tournament_name", "Torneo {format}").format(
        format=leg.format
    )
    hashtag = cfg.get("content.hashtag_grafica", "")

    def _slide(template, kind, etichetta, pagina, indice, totale, contesto, titolo):
        # Il numero di pagina compare solo quando ce n'e' piu' di una.
        suffisso = f"{indice + 1}/{totale}" if totale > 1 else fmt_date(day)
        nome = _stamp(cfg, etichetta, day, leg.format.lower().replace(" ", "-"))
        return render(
            cfg, template,
            {# La cornice comune: gli stessi slot delle card del calendario.
             "kicker_1": contesto, "kicker_2": suffisso,
             "badge": leg.format, "sopratitolo": "", "titolo": titolo,
             "righe": pagina,
             "link": _senza_schema(cfg.get("content.evento.link", "")),
             "invito": cfg.get("content.evento.invito", "Iscriviti"),
             "qr_image": cfg.get("content.evento.qr", ""),
             # Serviti al vecchio template su sfondo Canva, ancora disponibile:
             # li' il sottotitolo diceva la tappa, non l'occhiello.
             "leg": leg, "standings": standings, "title": torneo,
             "hashtag": hashtag, "rows": pagina,
             "row_style": cfg.get("posts.leg_results.row_style", "strip"),
             "subtitle": ((titolo if kind == "leg_results" else contesto)
                          + (f" · {indice + 1}/{totale}" if totale > 1 else "")),
             "background": _background(cfg, kind) or background,
             "density": _density(len(pagina))},
            f"{nome}-{indice + 1}" if totale > 1 else nome,
            size=post_size(cfg, kind),
        )

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

    immagini = [
        _slide(templates[0], "leg_results", "risultati", pagina, i,
               len(pagine_tappa),
               cfg.get("content.leg_kicker", "Risultati di tappa"),
               titolo_tappa)
        for i, pagina in enumerate(pagine_tappa)
    ] + [
        _slide(templates[1], "leg_results_standings", "classifica", pagina, i,
               len(pagine_classifica),
               cfg.get("content.standings_subtitle", "Classifica generale"),
               cfg.get("content.standings_title", "Classifica"))
        for i, pagina in enumerate(pagine_classifica)
    ]

    caption = render_caption(
        cfg, "leg_results",
        {"leg": leg, "rows": rows, "standings": standings,
         "standings_rows": standings_rows,
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
              "slide_classifica": len(pagine_classifica),
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
    "format_spotlight": format_spotlight,
    "leg_results": leg_results,
}

# Alcune giornate valgono piu' di un post: qui le pipeline che lo sanno fare.
PIPELINES_MULTI = {
    "leg_results": leg_results_batch,
}


def drafts(cfg: Config, kind: str, day: dt.date | None = None,
           **kwargs) -> list[PostDraft]:
    """Tutte le bozze che quel giorno richiede per quel tipo di post."""
    if kind in PIPELINES_MULTI:
        return PIPELINES_MULTI[kind](cfg, day, **kwargs)
    return [PIPELINES[kind](cfg, day, **kwargs)]
