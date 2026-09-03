"""Interfaccia a riga di comando: `momasocial <comando>`.

E' il punto d'ingresso usato sia dai workflow GitHub Actions sia dagli
slash command di Claude Code, cosi' che i due percorsi eseguano esattamente
lo stesso codice.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from . import __version__, config
from .errors import ConfigError, MtgSocialError, NoDataError
from .pipelines import PIPELINES
from .publish import publish_draft
from .timeutil import fmt_range, now, resolve_date, week_bounds

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
def cmd_post(args) -> int:
    cfg = config.load(args.config)
    pipeline = PIPELINES[args.kind]
    day = resolve_date(args.date, cfg.timezone) if args.date else None

    kwargs = {}
    if args.kind != "weekly_calendar" and args.format:
        kwargs["fmt"] = args.format

    try:
        draft = pipeline(cfg, day, **kwargs)
    except NoDataError as exc:
        print(f"[skip] {exc}", file=sys.stderr)
        _github_output(status="no-data", reason=str(exc))
        _summary(f"⏭️ **{args.kind}** saltato: {exc}")
        return EXIT_NO_DATA

    print(f"Immagini: {', '.join(draft.images)}")
    print("─" * 60)
    print(draft.caption)
    print("─" * 60)

    if args.no_publish:
        _github_output(status="drafted", images=";".join(draft.images))
        _summary(f"📝 **{args.kind}** generato (nessuna pubblicazione richiesta)")
        return EXIT_OK

    result = publish_draft(cfg, draft, dry_run=args.dry_run, force=args.force)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    _github_output(status=result["status"], post_id=result.get("post_id", ""))
    icon = {"published": "✅", "dry-run": "🧪", "skipped": "⏭️"}.get(result["status"], "⚠️")
    _summary(
        f"{icon} **{args.kind}** — {result['status']}"
        + (f" · [post]({result['permalink']})" if result.get("permalink") else "")
        + (f" · {result['reason']}" if result.get("reason") else "")
    )
    return EXIT_OK


def cmd_gate(args) -> int:
    """Cancello orario per i cron GitHub (che girano in UTC, senza DST).

    Ogni workflow schedula *due* cron (ora legale e ora solare) e delega a
    questo comando la decisione: gira solo se in Europe/Rome sono davvero
    le ore richieste. Cosi' il post esce sempre alle 10:00 locali, tutto l'anno.
    """
    cfg = config.load(args.config)
    local = now(cfg.timezone)
    ok = local.hour == args.hour
    if args.weekday is not None:
        ok = ok and local.weekday() == args.weekday
    print(f"{local.isoformat()} (ora locale {cfg.timezone}) -> run={'true' if ok else 'false'}")
    _github_output(run=str(ok).lower(), local_time=local.strftime("%Y-%m-%d %H:%M"))
    if not ok:
        _summary(f"⏱️ Scatto ignorato: in {cfg.timezone} sono le {local:%H:%M}, "
                 f"atteso {args.hour:02d}:00")
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
    check("Chromium", lambda: _find_chromium(cfg.get("render.chromium_path", "")))

    start, end = week_bounds(resolve_date("today", cfg.timezone))
    check(f"Sorgente eventi ({fmt_range(start, end)})",
          lambda: f"{len(fetch_events(cfg, start, end))} eventi")
    yesterday = resolve_date("yesterday", cfg.timezone)
    check(f"Sorgente risultati ({yesterday})",
          lambda: f"{len(fetch_leg_results(cfg, yesterday).rows)} righe")
    check("Sorgente classifiche",
          lambda: f"{len(fetch_standings(cfg, args.format or 'Modern').rows)} righe")

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


def _check_media(cfg, backend: str) -> str:
    if backend == "s3":
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
              "start_time": e.start_time, "venue": e.venue} for e in events],
            ensure_ascii=False, indent=2))
        return EXIT_OK
    print(f"Settimana {fmt_range(start, end)} — {len(events)} eventi")
    for group_day, group in events_by_day(events):
        print(f"\n{group_day.isoformat()} — {group[0].weekday}")
        for event in group:
            print(f"  {event.start_time or '  —  '}  {event.label}  [{event.format}]"
                  f"{'  @' + event.venue if event.venue else ''}")
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
        ("format", "format_spotlight", "post formato del giorno (mer/gio 10:00)"),
        ("results", "leg_results", "carosello risultati + classifica (gio/ven 03:00)"),
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

    p = sub.add_parser("gate", help="verifica che sia l'ora locale giusta (per i cron)")
    p.set_defaults(func=cmd_gate)
    p.add_argument("--hour", type=int, required=True, help="ora attesa in fuso locale")
    p.add_argument("--weekday", type=int, default=None, help="0=lunedi ... 6=domenica")

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
