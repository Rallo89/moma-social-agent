"""Interfaccia a riga di comando: `momasocial <comando>`.

E' il punto d'ingresso usato sia dai workflow GitHub Actions sia dagli
slash command di Claude Code, cosi' che i due percorsi eseguano esattamente
lo stesso codice.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
from pathlib import Path

from . import __version__, config
from .errors import ConfigError, MtgSocialError, NoDataError
from .pipelines import drafts
from .publish import publish_draft
from .timeutil import (
    fmt_range,
    is_monthly_run_day,
    now,
    resolve_date,
    week_bounds,
)

EXIT_OK = 0
EXIT_ERROR = 1
EXIT_NO_DATA = 78  # skip pulito: nessun dato, non e' un fallimento


def _github_output(**values) -> None:
    """Espone i risultati agli step successivi del workflow."""
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as handle:
        for key, value in values.items():
            handle.write(f"{key}={value}\n")


def _summary(text: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(text + "\n")


# ── comandi ─────────────────────────────────────────────────────────────────
def _genera(cfg, kind, day, kwargs, args) -> list[tuple[str, str]]:
    """Genera i post di una giornata e, se richiesto, li pubblica.

    Restituisce un (esito, nota) per post: una serata con due tornei ne
    produce due.
    """
    try:
        bozze = drafts(cfg, kind, day, **kwargs)
    except NoDataError as exc:
        return [("no-data", str(exc))]

    esiti = []
    for draft in bozze:
        etichetta = draft.meta.get("leg") or draft.meta.get("format", "")
        if len(bozze) > 1 and etichetta:
            print(f"» {etichetta}")
        print(f"Immagini: {', '.join(draft.images)}")
        print("-" * 60)
        print(draft.caption)
        print("-" * 60)

        if args.no_publish:
            esiti.append(("drafted", f"{len(draft.images)} slide"
                          + (f" · {etichetta}" if etichetta else "")))
            continue

        result = publish_draft(cfg, draft, dry_run=args.dry_run, force=args.force)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        esiti.append((result["status"],
                      result.get("reason") or result.get("permalink", "")))
    return esiti


def _post_di_una_settimana(cfg, kind, kwargs, args, day) -> int:
    """Un post per ogni giornata di gioco della settimana.

    Serve a rigenerare un arretrato, o a rivedere una settimana intera dopo
    aver corretto qualcosa, senza lanciare il comando giorno per giorno.
    """
    inizio, fine = week_bounds(day or resolve_date("today", cfg.timezone))
    print(f"Settimana {fmt_range(inizio, fine)}\n")

    giornate = (fine - inizio).days + 1
    esiti = []
    for scarto in range(giornate):
        giorno = inizio + dt.timedelta(days=scarto)
        try:
            risultati = _genera(cfg, kind, giorno, kwargs, args)
        except MtgSocialError as exc:
            # Un giorno che fallisce non deve far perdere gli altri sei: si
            # annota e si prosegue, poi il riepilogo lo dichiara.
            risultati = [("error", str(exc))]
            print(f"[errore] {giorno.isoformat()}: {exc}", file=sys.stderr)
        esiti.extend((giorno, esito, nota) for esito, nota in risultati)
        if any(esito != "no-data" for esito, _ in risultati):
            print()

    icone = {"drafted": "[gen]", "published": "[pub]", "dry-run": "[test]",
             "skipped": "[skip]", "error": "[err]", "no-data": "[   ]"}
    # Ogni giornata compare nell'elenco con il suo perche': un giorno senza
    # post e' un'informazione, non silenzio. Solo i post davvero prodotti
    # entrano nel conteggio.
    prodotti = [riga for riga in esiti if riga[1] not in ("no-data", "error")]
    print("-" * 60)
    for giorno, esito, nota in esiti:
        print(f"{icone.get(esito, '     ')} {giorno.isoformat()}  {esito}"
              + (f"  {nota}" if nota else ""))
    # Un giorno fallito non e' un giorno senza tappe: le due cose si contano
    # separate, altrimenti una sorgente giu' si traveste da settimana tranquilla.
    senza = [riga for riga in esiti if riga[1] == "no-data"]
    falliti = [g for g, e, _ in esiti if e == "error"]
    print(f"\n{len(prodotti)} post su {giornate} giornate "
          f"({len(senza)} senza tappe"
          + (f", {len(falliti)} fallit{'a' if len(falliti) == 1 else 'e'}"
             if falliti else "") + ")")

    if falliti:
        print(f"{len(falliti)} giornate fallite: "
              f"{', '.join(g.isoformat() for g in falliti)}", file=sys.stderr)

    _github_output(status="week", prodotti=str(len(prodotti)),
                   falliti=str(len(falliti)))
    _summary(f"Settimana {fmt_range(inizio, fine)}: {len(prodotti)} post generati"
             + (f", {len(falliti)} falliti" if falliti else ""))
    if falliti:
        return EXIT_ERROR
    return EXIT_OK if prodotti else EXIT_NO_DATA


def cmd_post(args) -> int:
    cfg = config.load(args.config)
    day = resolve_date(args.date, cfg.timezone) if args.date else None

    kwargs = {}
    if args.kind != "weekly_calendar" and args.format:
        kwargs["fmt"] = args.format
    if args.kind == "leg_results" and getattr(args, "no_meta", False):
        kwargs["senza_meta"] = True

    if getattr(args, "settimana", False):
        return _post_di_una_settimana(cfg, args.kind, kwargs, args, day)

    risultati = _genera(cfg, args.kind, day, kwargs, args)
    if all(esito == "no-data" for esito, _ in risultati):
        nota = risultati[0][1]
        print(f"[skip] {nota}", file=sys.stderr)
        _github_output(status="no-data", reason=nota)
        _summary(f"Saltato **{args.kind}**: {nota}")
        return EXIT_NO_DATA

    esiti = ", ".join(esito for esito, _ in risultati)
    _github_output(status=esiti, post=str(len(risultati)))
    for esito, nota in risultati:
        _summary(f"**{args.kind}** - {esito}" + (f" - {nota}" if nota else ""))
    return EXIT_OK


def cmd_gate(args) -> int:
    """Cancello orario per i cron GitHub (che girano in UTC, senza DST).

    I cron si schedulano in UTC e l'ora legale li sposta di un'ora: e' questo
    comando a decidere, guardando che ore sono davvero in Europe/Rome.

    Con `--recupera` l'ora richiesta diventa un "non prima di". Serve perche'
    i cron di GitHub sono a sforzo migliore e non a orario: su questo repo
    hanno girato con quattro, sei, anche sette ore di ritardo. Preteso l'orario
    esatto non passava nessuno scatto, i workflow risultavano verdi e non
    usciva un post. Il doppione lo impedisce il registro delle pubblicazioni,
    non il cancello: il primo scatto della giornata pubblica, gli altri
    trovano la chiave gia' usata e si fermano.
    """
    cfg = config.load(args.config)
    local = now(cfg.timezone)
    recupera = getattr(args, "recupera", False)
    ok = local.hour >= args.hour if recupera else local.hour == args.hour
    if args.weekday is not None:
        ok = ok and local.weekday() == args.weekday
    if getattr(args, "day_of_month", None) is not None:
        ok = ok and is_monthly_run_day(local.date(), args.day_of_month)
    print(f"{local.isoformat()} (ora locale {cfg.timezone}) -> run={'true' if ok else 'false'}")
    _github_output(run=str(ok).lower(), local_time=local.strftime("%Y-%m-%d %H:%M"))
    if not ok:
        atteso = f"dalle {args.hour:02d}:00" if recupera else f"le {args.hour:02d}:00"
        _summary(f"⏱️ Scatto ignorato: in {cfg.timezone} sono le {local:%H:%M}, "
                 f"atteso {atteso}")
    return EXIT_OK


def cmd_media_test(args) -> int:
    """Carica un PNG sull'hosting e verifica che sia scaricabile davvero.

    E' il collaudo che separa i due problemi: se il file si carica ma non si
    scarica, l'errore e' nell'hosting e non ha senso cercarlo su Instagram.
    Meta scarica l'immagine da un URL pubblico, senza credenziali: se non
    riesce a prenderla, il container va in ERROR con un messaggio generico.
    """
    import requests

    from .uploader import upload

    cfg = config.load(args.config)
    if args.file:
        path = Path(args.file)
    else:
        out = cfg.resolve_path(cfg.get("render.output_dir", "out"))
        png = sorted(out.rglob("*.png"), key=lambda p: p.stat().st_mtime)
        if not png:
            raise ConfigError(
                f"Nessun PNG in {out}: genera prima un post "
                "(momasocial weekly --no-publish) o passa --file."
            )
        path = png[-1]
    if not path.exists():
        raise ConfigError(f"File inesistente: {path}")

    backend = cfg.get("media.backend", "none")
    print(f"Backend: {backend}")
    print(f"File:    {path} ({path.stat().st_size / 1024:.0f} KB)")

    url = upload(cfg, path)
    print(f"URL:     {url}")

    # La verifica va fatta senza credenziali, come la fa Meta.
    try:
        risposta = requests.get(url, timeout=60, stream=True)
    except requests.RequestException as exc:
        print(f"[errore] l'URL non e' raggiungibile: {exc}", file=sys.stderr)
        return EXIT_ERROR

    tipo = risposta.headers.get("Content-Type", "")
    lunghezza = risposta.headers.get("Content-Length", "?")
    print(f"Risposta: {risposta.status_code} · {tipo} · {lunghezza} byte")

    if risposta.status_code != 200:
        print(f"[errore] Meta si aspetta 200, ha ricevuto {risposta.status_code}: "
              "l'oggetto non e' pubblico o l'URL e' sbagliato.", file=sys.stderr)
        return EXIT_ERROR
    if not tipo.startswith("image/"):
        print(f"[errore] Content-Type '{tipo}' invece di image/*: quasi sempre "
              "una pagina di login o un errore travestito da 200.",
              file=sys.stderr)
        return EXIT_ERROR

    print("\nOK: Instagram riuscirebbe a scaricare questa immagine.")
    return EXIT_OK


def _chiedi_meta(url: str, params: dict, cosa: str) -> dict:
    """Una GET verso Meta che spiega quale passaggio e' fallito."""
    import requests

    try:
        risposta = requests.get(url, params=params, timeout=60)
        dati = risposta.json()
    except (requests.RequestException, ValueError) as exc:
        raise ConfigError(f"{cosa}: Meta irraggiungibile ({exc})") from exc
    if "error" in dati:
        errore = dati["error"]
        messaggio = errore.get("message") if isinstance(errore, dict) else errore
        codice = errore.get("code") if isinstance(errore, dict) else ""
        raise ConfigError(f"{cosa}: {messaggio}" + (f" (code {codice})" if codice else ""))
    if "error_message" in dati:      # graph.instagram.com usa un altro formato
        raise ConfigError(f"{cosa}: {dati['error_message']}")
    return dati


def _scadenza(cfg, secondi) -> str:
    if not secondi:
        return ""
    giorno = (now(cfg.timezone) + dt.timedelta(seconds=int(secondi))).date()
    return giorno.isoformat()


def _setup_instagram_login(cfg, args) -> int:
    """Percorso Instagram Login: nessuna Pagina Facebook di mezzo.

    Due chiamate: il token breve diventa da 60 giorni, e da /me si legge
    l'id dell'account su cui pubblicare.
    """
    segreto = args.app_secret or os.environ.get("IG_APP_SECRET", "")
    if not segreto:
        raise ConfigError(
            "Serve la Chiave segreta di Instagram (non quella dell'app "
            "Facebook): passala con --app-secret o mettila nel .env come "
            "IG_APP_SECRET. Si trova in Casi d'uso > API Instagram > "
            "Configurazione dell'API con Instagram login."
        )

    # Lo scambio vale per un token breve. La console di Meta a volte ne
    # consegna gia' uno a lunga durata, e in quel caso lo scambio fallisce: e'
    # un vicolo cieco evitabile, perche' quel token va bene com'e'. Si prova,
    # e se non funziona si tiene quello che c'e' — tanto la chiamata dopo
    # verifica comunque che apra l'account.
    token, quando = args.token, ""
    try:
        scambio = _chiedi_meta(
            "https://graph.instagram.com/access_token",
            {"grant_type": "ig_exchange_token",
             "client_secret": segreto,
             "access_token": args.token},
            "Scambio del token",
        )
    except ConfigError as exc:
        print(f"[avviso] lo scambio non e' riuscito: {exc}")
        print("[avviso] proseguo con il token cosi' com'e'. Se la console te "
              "l'ha gia' dato a lunga durata va bene, ma se la chiave segreta "
              "era sbagliata questo token potrebbe durare un'ora: controlla "
              "IG_APP_SECRET, e se i post si fermano subito e' questa la causa.")
    else:
        token = scambio.get("access_token", "") or args.token
        quando = _scadenza(cfg, scambio.get("expires_in"))
    print("Token long-lived ottenuto" + (f", scade il {quando}" if quando else ""))

    versione = cfg.get("instagram.api_version", "v21.0")
    io = _chiedi_meta(
        f"https://graph.instagram.com/{versione}/me",
        {"fields": "id,username", "access_token": token},
        "Lettura dell'account",
    )
    print(f"Instagram: @{io.get('username')}")
    print("\nDa incollare nel .env e nei secret di GitHub:\n")
    print(f"IG_USER_ID={io.get('id')}")
    print(f"IG_ACCESS_TOKEN={token}")
    print("\nIl token e' una credenziale: non finisce su git e non si "
          "incolla in chat.")
    return EXIT_OK


def _setup_facebook_login(cfg, args) -> int:
    """Percorso Facebook Login: l'id Instagram si chiede alla Pagina."""
    versione = cfg.get("instagram.api_version", "v21.0")
    base = f"https://graph.facebook.com/{versione}"

    app_id = args.app_id or os.environ.get("FB_APP_ID", "")
    app_secret = args.app_secret or os.environ.get("FB_APP_SECRET", "")
    if not (app_id and app_secret):
        raise ConfigError(
            "Servono l'ID e il segreto dell'app Meta: passali con --app-id e "
            "--app-secret, oppure mettili nel .env come FB_APP_ID e "
            "FB_APP_SECRET. Si trovano in Impostazioni dell'app > Di base."
        )

    scambio = _chiedi_meta(f"{base}/oauth/access_token", {
        "grant_type": "fb_exchange_token",
        "client_id": app_id,
        "client_secret": app_secret,
        "fb_exchange_token": args.token,
    }, "Scambio del token")
    token = scambio.get("access_token", "")
    if not token:
        raise ConfigError("Scambio del token: risposta senza access_token")
    quando = _scadenza(cfg, scambio.get("expires_in"))
    print("Token long-lived ottenuto" + (f", scade il {quando}" if quando else ""))

    # L'id Instagram non si chiede a Instagram: si chiede alla Pagina.
    pagine = _chiedi_meta(f"{base}/me/accounts", {
        "fields": "name,instagram_business_account{id,username}",
        "access_token": token,
    }, "Elenco delle Pagine").get("data", [])
    if not pagine:
        raise ConfigError(
            "Nessuna Pagina Facebook visibile. O l'account non ne amministra "
            "nessuna, o al token manca il permesso pages_show_list."
        )

    collegate = [p for p in pagine if p.get("instagram_business_account")]
    if not collegate:
        nomi = ", ".join(p.get("name", "?") for p in pagine)
        raise ConfigError(
            f"Nessuna delle Pagine ({nomi}) ha un account Instagram "
            "professionale collegato. Va collegato dalle impostazioni della "
            "Pagina, e l'account Instagram dev'essere Business o Creator."
        )
    if args.page:
        collegate = [p for p in collegate
                     if args.page in (p.get("id"), p.get("name"))]
        if not collegate:
            raise ConfigError(f"Nessuna Pagina corrisponde a {args.page!r}")
    if len(collegate) > 1:
        print("\nPiu' di una Pagina ha un account Instagram collegato:")
        for p in collegate:
            ig = p["instagram_business_account"]
            print(f"  {p.get('name')} (id {p.get('id')}) "
                  f"-> @{ig.get('username')}")
        raise ConfigError("Rilancia indicando quale, con --page <nome o id>")

    pagina = collegate[0]
    ig = pagina["instagram_business_account"]
    print(f"Pagina: {pagina.get('name')}")
    print(f"Instagram: @{ig.get('username')}")
    print("\nDa incollare nel .env e nei secret di GitHub:\n")
    print(f"IG_USER_ID={ig.get('id')}")
    print(f"IG_ACCESS_TOKEN={token}")
    print("\nIl token e' una credenziale: non finisce su git e non si "
          "incolla in chat.")
    return EXIT_OK


def cmd_ig_setup(args) -> int:
    """Ricava IG_USER_ID e un token long-lived da un token breve.

    E' il passaggio piu' scomodo della configurazione, e cambia a seconda di
    come ci si autentica: farlo qui permette di dire quale chiamata e' andata
    storta, invece di lasciare l'utente davanti a un JSON di errore di Meta.
    """
    cfg = config.load(args.config)
    host = args.host or cfg.get("instagram.api_host", "graph.facebook.com")
    if "graph.instagram.com" in host:
        return _setup_instagram_login(cfg, args)
    return _setup_facebook_login(cfg, args)


def cmd_ig_refresh(args) -> int:
    """Allunga di altri 60 giorni un token Instagram Login gia' long-lived.

    Solo per il percorso Instagram: quello Facebook si rinnova ripetendo lo
    scambio con un token fresco dell'Explorer.
    """
    cfg = config.load(args.config)
    host = cfg.get("instagram.api_host", "graph.facebook.com")
    if "graph.instagram.com" not in host:
        raise ConfigError(
            "Il rinnovo diretto esiste solo per Instagram Login. Con "
            "graph.facebook.com si rigenera un token nel Graph API Explorer e "
            "si rilancia `momasocial ig-setup`."
        )
    token = args.token or cfg.get("instagram.access_token", "")
    if not token:
        raise ConfigError("Nessun token da rinnovare: passalo con --token o "
                          "valorizza IG_ACCESS_TOKEN nel .env")

    dati = _chiedi_meta("https://graph.instagram.com/refresh_access_token",
                        {"grant_type": "ig_refresh_token", "access_token": token},
                        "Rinnovo del token")
    nuovo = dati.get("access_token", "")
    if not nuovo:
        raise ConfigError("Rinnovo del token: risposta senza access_token")
    quando = _scadenza(cfg, dati.get("expires_in"))
    print("Token rinnovato" + (f", scade il {quando}" if quando else ""))
    print("\nAggiorna IG_ACCESS_TOKEN nel .env e nei secret di GitHub:\n")
    print(f"IG_ACCESS_TOKEN={nuovo}")
    return EXIT_OK


def cmd_token_status(args) -> int:
    """Il token e' ancora buono, e per quanto?

    La logica sta qui e non dentro il workflow: in YAML non si testa, e questo
    controllo e' l'unica cosa che sta fra una scadenza e cinque post fermi
    senza che nessuno se ne accorga.
    """
    cfg = config.load(args.config)
    token = args.token or cfg.get("instagram.access_token", "")
    if not token:
        raise ConfigError("Nessun token da controllare (IG_ACCESS_TOKEN)")
    host = cfg.get("instagram.api_host", "graph.facebook.com")
    versione = cfg.get("instagram.api_version", "v21.0")

    if "graph.instagram.com" in host:
        # Qui non esiste un debug_token: si puo' solo chiedere se il token
        # apre ancora l'account. Quanto gli resti da vivere non si sa, ed e'
        # il motivo per cui il rinnovo va fatto a calendario, non a scadenza.
        try:
            io = _chiedi_meta(f"https://graph.instagram.com/{versione}/me",
                              {"fields": "id,username", "access_token": token},
                              "Controllo del token")
        except ConfigError as exc:
            stato, giorni, nota = "invalid", 0, str(exc)
        else:
            stato, giorni, nota = "ok", -1, f"@{io.get('username')}"
    else:
        dati = _chiedi_meta(f"https://graph.facebook.com/{versione}/debug_token",
                            {"input_token": token, "access_token": token},
                            "Controllo del token").get("data", {})
        if not dati.get("is_valid"):
            stato, giorni, nota = "invalid", 0, "Meta lo dichiara non valido"
        elif not dati.get("expires_at"):
            stato, giorni, nota = "ok", -1, "senza scadenza dichiarata"
        else:
            import time
            giorni = int((dati["expires_at"] - time.time()) // 86400)
            stato = "expiring" if giorni < args.soglia else "ok"
            nota = f"scade fra {giorni} giorni"

    print(f"{stato}: {nota}")
    _github_output(state=stato, days=str(giorni))
    return EXIT_OK


def cmd_doctor(args) -> int:
    """Diagnosi completa: config, sorgenti dati, rendering, credenziali."""
    cfg = config.load(args.config)
    from .instagram import InstagramClient
    from .render import _find_chromium
    from .repos import fetch_events, fetch_leg_results, fetch_standings

    # ok | warn | fail — "questa settimana non si gioca" e' un esito normale
    # della sorgente, non un guasto da segnalare come rosso.
    checks: list[tuple[str, str, str]] = []

    def check(label, fn):
        try:
            checks.append((label, "ok", str(fn())))
        except NoDataError as exc:
            checks.append((label, "warn", f"nessun dato: {exc}"))
        except Exception as exc:  # noqa: BLE001 - il doctor riporta tutto
            checks.append((label, "fail", f"{type(exc).__name__}: {exc}"))

    check("Config caricata", lambda: cfg.path)

    # Un ${VAR} non impostato non fa rumore: diventa stringa vuota e il guasto
    # arriva dopo, come 401 della sorgente o credenziale rifiutata. Qui si
    # nomina prima. E' un warn e non un fail: di CANVA_* o delle chiavi S3 si
    # fa a meno, dipende da cosa e' acceso in config.
    def variabili():
        if cfg.env_mancanti:
            raise ConfigError("citate in config ma non impostate: "
                              + ", ".join(cfg.env_mancanti))
        return "tutte impostate"
    try:
        checks.append(("Variabili d'ambiente", "ok", variabili()))
    except ConfigError as exc:
        checks.append(("Variabili d'ambiente", "warn", str(exc)))
    check("Chromium", lambda: _find_chromium(cfg.get("render.chromium_path", "")))

    oggi = resolve_date("today", cfg.timezone)
    start, end = week_bounds(oggi)
    check(f"Sorgente eventi ({fmt_range(start, end)})",
          lambda: f"{len(fetch_events(cfg, start, end))} eventi")

    # Sondare "ieri" segnala un problema anche quando semplicemente non si e'
    # giocato: si cerca invece l'ultima giornata di gioco realmente passata.
    giorno, motivo = _ultima_giornata(cfg, oggi)
    check(f"Sorgente risultati ({giorno}, {motivo})",
          lambda: f"{len(fetch_leg_results(cfg, giorno).rows)} righe")

    formato, lega, etichetta = _classifica_da_provare(cfg, oggi, giorno, args.format)
    check(f"Sorgente classifiche ({etichetta})",
          lambda: f"{len(fetch_standings(cfg, formato, league=lega).rows)} righe")

    backend = cfg.get("media.backend", "none")
    check(f"Hosting immagini ({backend})", lambda: _check_media(cfg, backend))
    if cfg.get("instagram.enabled", True):
        check("Credenziali Instagram", lambda: InstagramClient(cfg).check())

    icons = {"ok": "✅", "warn": "⚠️ ", "fail": "❌"}
    width = max(len(label) for label, _, _ in checks)
    failed = sum(1 for _, state, _ in checks if state == "fail")
    for label, state, detail in checks:
        print(f"{icons[state]} {label.ljust(width)}  {detail}")
    print(f"\n{len(checks) - failed}/{len(checks)} controlli superati")
    return EXIT_OK if failed == 0 else EXIT_ERROR


def _ultima_giornata(cfg, oggi):
    """Ultimo giorno con un evento in calendario, per sondare i risultati."""
    from .repos import fetch_events

    try:
        passati = [e.date for e in fetch_events(cfg, oggi - dt.timedelta(days=60), oggi)
                   if e.date < oggi]
    except MtgSocialError:
        passati = []
    if passati:
        return max(passati), "ultima giornata in calendario"
    return resolve_date("yesterday", cfg.timezone), "ieri, nessun evento recente in calendario"


def _formato_da_provare(cfg, oggi) -> str:
    """Un formato che esiste davvero in calendario, invece di indovinarlo."""
    from .repos import fetch_events, formats_on

    try:
        eventi = fetch_events(cfg, oggi - dt.timedelta(days=60),
                              oggi + dt.timedelta(days=30))
    except MtgSocialError:
        return "Modern"
    formati = formats_on(eventi)
    return formati[0] if formati else "Modern"


def _classifica_da_provare(cfg, oggi, giorno, formato_forzato: str = ""):
    """Formato e lega su cui sondare la classifica.

    La pipeline non chiede mai "la classifica del Pauper": chiede quella della
    lega a cui appartiene la tappa appena giocata. Sondare per solo formato
    farebbe arrivare insieme tutte le stagioni — Pauper Autumn 2024, Spring
    2025, Fall 2026 — e il doctor segnalerebbe rosso su un sistema sano.
    """
    from .repos import fetch_leg_results_all

    if not formato_forzato:
        try:
            tappe = fetch_leg_results_all(cfg, giorno)
        except MtgSocialError:
            tappe = []
        for tappa in tappe:
            if tappa.league:
                return (tappa.format, tappa.league,
                        f"{tappa.format}, lega della tappa del {giorno}")
    formato = formato_forzato or _formato_da_provare(cfg, oggi)
    return formato, "", f"formato '{formato}', nessuna lega da cui partire"


def _check_media(cfg, backend: str) -> str:
    if backend == "s3":
        # Il bucket configurato non basta: senza boto3 l'upload fallisce lo
        # stesso, e una spia verde che mente e' peggio di nessuna spia.
        import importlib.util

        from .uploader import MANCA_BOTO3

        if importlib.util.find_spec("boto3") is None:
            raise ConfigError(MANCA_BOTO3)
        if not cfg.get("media.s3.bucket"):
            raise ConfigError("media.s3.bucket vuoto (MEDIA_BUCKET)")
        return f"bucket {cfg.get('media.s3.bucket')}"
    if backend == "imgbb":
        if not cfg.get("media.imgbb.api_key"):
            raise ConfigError("media.imgbb.api_key vuoto (IMGBB_API_KEY)")
        return "api key presente"
    raise ConfigError("nessun backend configurato: la pubblicazione fallira'")


def cmd_canva_auth(args) -> int:
    """Autorizzazione una tantum verso Canva (apre il browser)."""
    from .canva import authorize

    cfg = config.load(args.config)
    path = authorize(cfg, open_browser=not args.no_browser)
    print(f"\nToken salvati in {path}")
    print("Da ora puoi lanciare: momasocial canva-sync")
    return EXIT_OK


def cmd_canva_sync(args) -> int:
    """Riesporta da Canva gli sfondi configurati."""
    from .canva import sync

    cfg = config.load(args.config)
    report = sync(cfg, only=args.only, check=args.check)

    width = max(len(row["nome"]) for row in report)
    icons = {"aggiornato": "⬇️ ", "da aggiornare": "🔸", "invariato": "✅"}
    for row in report:
        size = f"{row['byte'] / 1024:.0f} KB"
        print(f"{icons.get(row['stato'], '  ')} {row['nome'].ljust(width)}  "
              f"{row['stato']}  ({size}) → {row['file']}")

    changed = [r for r in report if r["stato"] != "invariato"]
    if args.check:
        print(f"\n{len(changed)}/{len(report)} sfondi da aggiornare (nessun file scritto)")
    elif changed:
        print(f"\n{len(changed)} sfondi aggiornati. Rigenera i post e controlla i PNG:")
        print("  momasocial weekly --no-publish")
        print("Poi committa i file in templates/images/assets/.")
    else:
        print("\nTutti gli sfondi erano gia' aggiornati.")
    return EXIT_OK


def cmd_schema(args) -> int:
    """Elenca tabelle e colonne di un endpoint PostgREST (Supabase).

    Serve a scrivere la sezione [sources.*.map] senza copiare i nomi delle
    colonne a mano dalla dashboard.
    """
    import os

    from .sources import describe_postgrest

    cfg = config.load(args.config)
    url = args.url or cfg.get("sources.results.url", "").split("/rest/v1")[0] + "/rest/v1/"
    chiave = args.key or os.environ.get("SUPABASE_KEY", "")
    if not url.strip("/"):
        raise ConfigError("Indica l'endpoint con --url, es. https://<ref>.supabase.co/rest/v1/")
    if not chiave:
        raise ConfigError("Chiave mancante: valorizza SUPABASE_KEY nel .env o usa --key")

    tabelle = describe_postgrest(
        url, {"apikey": chiave, "Authorization": f"Bearer {chiave}"}
    )
    for tabella, colonne in tabelle.items():
        print(f"\n{tabella}")
        for colonna in colonne:
            print(f"  · {colonna}")
    print(f"\n{len(tabelle)} tabelle. Usa questi nomi in [sources.*.map] "
          f"(vedi docs/SUPABASE.md).")
    return EXIT_OK


def cmd_agenda(args) -> int:
    """Cosa c'e' in programma: utile per decidere a mano cosa postare."""
    cfg = config.load(args.config)
    from .models import event_label, format_fee
    from .repos import events_by_day, fetch_events

    day = resolve_date(args.date or "today", cfg.timezone)
    start, end = week_bounds(day)
    try:
        events = fetch_events(cfg, start, end)
    except NoDataError as exc:
        print(f"[skip] {exc}")
        return EXIT_NO_DATA
    if args.json:
        print(json.dumps(
            [{"date": e.date.isoformat(), "title": e.title, "format": e.format,
              "league": e.league, "stage": e.stage, "final": e.is_final,
              "entry_fee": e.entry_fee, "start_time": e.start_time,
              "venue": e.venue, "address": e.address} for e in events],
            ensure_ascii=False, indent=2))
        return EXIT_OK
    print(f"Settimana {fmt_range(start, end)} — {len(events)} eventi")
    for group_day, group in events_by_day(events):
        print(f"\n{group_day.isoformat()} — {group[0].weekday}")
        for event in group:
            # Si mostra quello che finira' sulla card, non la riga grezza:
            # se qui il titolo o la quota sono sbagliati, lo sono anche li'.
            print(f"  {event.start_time or '  —  '}  {event_label(event)}"
                  f"  [{event.format}]"
                  f"{'  @' + event.venue if event.venue else ''}"
                  f"{'  ' + format_fee(event.entry_fee) if event.entry_fee else ''}")
    return EXIT_OK


# ── parser ──────────────────────────────────────────────────────────────────
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="momasocial",
        description="Agente social per tornei Magic: The Gathering",
    )
    parser.add_argument("--version", action="version", version=f"moma-social {__version__}")
    parser.add_argument("-c", "--config", default=None, help="path a un config alternativo")
    sub = parser.add_subparsers(dest="command", required=True)

    for name, kind, help_text in (
        ("weekly", "weekly_calendar", "post calendario settimanale (lunedi 10:00)"),
        ("monthly", "monthly_calendar",
         "post calendario del mese successivo (il 30, 10:00)"),
        ("standings", "standings_update",
         "carosello aggiornamento classifiche di lega (lunedi 10:00)"),
        ("format", "format_spotlight", "post formato del giorno (mer/gio 10:00)"),
        ("results", "leg_results", "carosello risultati + meta della tappa (gio/ven 03:00)"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.set_defaults(func=cmd_post, kind=kind)
        p.add_argument("--date", help="today | yesterday | AAAA-MM-GG (default per pipeline)")
        p.add_argument("--format", default="", help="forza il formato di gioco")
        p.add_argument("--dry-run", action="store_true", help="genera ma non pubblica")
        p.add_argument("--no-publish", action="store_true",
                       help="genera i file e basta, senza toccare il ledger")
        p.add_argument("--force", action="store_true",
                       help="pubblica anche se il dedupe dice gia' fatto")
        p.add_argument("--settimana", action="store_true",
                       help="un post per ogni giornata di gioco della settimana di --date")
        if kind == "leg_results":
            p.add_argument("--no-meta", action="store_true", dest="no_meta",
                           help="solo le slide dei risultati, senza il meta")

    p = sub.add_parser("gate", help="verifica che sia l'ora locale giusta (per i cron)")
    p.set_defaults(func=cmd_gate)
    p.add_argument("--hour", type=int, required=True, help="ora attesa in fuso locale")
    p.add_argument("--weekday", type=int, default=None, help="0=lunedi ... 6=domenica")
    p.add_argument("--day-of-month", type=int, default=None, dest="day_of_month",
                   help="giorno del mese; nei mesi piu' corti vale l'ultimo")
    p.add_argument("--recupera", action="store_true",
                   help="--hour diventa 'non prima di': lascia passare anche uno "
                        "scatto in ritardo, tanto il doppione lo blocca il registro")

    p = sub.add_parser("media-test",
                       help="carica un PNG sull'hosting e verifica che sia scaricabile")
    p.set_defaults(func=cmd_media_test)
    p.add_argument("--file", default="",
                   help="PNG da caricare (default: l'ultimo generato in out/)")

    p = sub.add_parser("ig-setup",
                       help="ricava IG_USER_ID e token long-lived da un token breve")
    p.set_defaults(func=cmd_ig_setup)
    p.add_argument("--token", required=True,
                   help="token breve preso dal Graph API Explorer")
    p.add_argument("--app-id", default="", dest="app_id",
                   help="ID dell'app Meta (default: FB_APP_ID dal .env)")
    p.add_argument("--app-secret", default="", dest="app_secret",
                   help="segreto dell'app Meta (default: FB_APP_SECRET dal .env)")
    p.add_argument("--page", default="",
                   help="nome o id della Pagina, se ne amministrate piu' d'una")
    p.add_argument("--host", default="",
                   help="forza il percorso: graph.instagram.com o graph.facebook.com")

    p = sub.add_parser("token-status",
                       help="il token Instagram e' ancora valido? per quanto?")
    p.set_defaults(func=cmd_token_status)
    p.add_argument("--token", default="", help="default: quello configurato")
    p.add_argument("--soglia", type=int, default=14,
                   help="giorni sotto i quali dichiararlo in scadenza")

    p = sub.add_parser("ig-refresh",
                       help="allunga di 60 giorni il token (solo Instagram Login)")
    p.set_defaults(func=cmd_ig_refresh)
    p.add_argument("--token", default="",
                   help="token da rinnovare (default: quello configurato)")

    p = sub.add_parser("doctor", help="diagnosi di configurazione, dati e credenziali")
    p.set_defaults(func=cmd_doctor)
    p.add_argument("--format", default="", help="formato da usare per il test classifiche")

    p = sub.add_parser("canva-auth",
                       help="autorizza l'accesso a Canva (una volta sola)")
    p.set_defaults(func=cmd_canva_auth)
    p.add_argument("--no-browser", action="store_true",
                   help="non aprire il browser, stampa solo l'indirizzo")

    p = sub.add_parser("canva-sync", help="riesporta da Canva gli sfondi configurati")
    p.set_defaults(func=cmd_canva_sync)
    p.add_argument("--only", default="",
                   help="sincronizza un solo sfondo (nome file, path o design_id)")
    p.add_argument("--check", action="store_true",
                   help="mostra cosa cambierebbe senza scrivere nulla")

    p = sub.add_parser("schema",
                       help="elenca tabelle e colonne di un endpoint Supabase/PostgREST")
    p.set_defaults(func=cmd_schema)
    p.add_argument("--url", default="", help="https://<ref>.supabase.co/rest/v1/")
    p.add_argument("--key", default="", help="chiave anon (default: $SUPABASE_KEY)")

    p = sub.add_parser("agenda", help="elenca gli eventi della settimana")
    p.set_defaults(func=cmd_agenda)
    p.add_argument("--date", help="giorno dentro la settimana da mostrare")
    p.add_argument("--json", action="store_true")

    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except MtgSocialError as exc:
        print(f"[errore] {type(exc).__name__}: {exc}", file=sys.stderr)
        _summary(f"❌ **{getattr(args, 'kind', args.command)}** — {exc}")
        _github_output(status="error", reason=str(exc))
        return EXIT_ERROR


if __name__ == "__main__":  # pragma: no cover
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    raise SystemExit(main())
