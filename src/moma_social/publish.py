"""Dal draft al post pubblicato, con tracciamento e idempotenza.

Ogni pubblicazione lascia una riga in out/published.jsonl. Prima di pubblicare
si controlla se lo stesso `dedupe_key` e' gia' uscito: un workflow rilanciato
a mano (o un doppio scatto del cron) non produce un doppione sul profilo.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from .config import Config
from .errors import PublishError
from .instagram import InstagramClient
from .models import PostDraft
from .uploader import upload_all

DEFAULT_LEDGER = "state/published.jsonl"


def ledger_path(cfg: Config) -> Path:
    """Il ledger e' versionato: e' la memoria di cosa e' gia' uscito.

    Vive fuori da `out/` (che e' git-ignored e sparisce a ogni run in CI)
    proprio perche' il controllo anti-doppione deve valere fra un'esecuzione
    e l'altra, non solo dentro la stessa.
    """
    path = cfg.resolve_path(cfg.get("publish.ledger", DEFAULT_LEDGER))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def dedupe_key(draft: PostDraft) -> str:
    meta = draft.meta
    scope = (meta.get("day") or meta.get("week_start")
             or meta.get("month_start") or "")
    # Il nome del torneo entra nella chiave perche' due leghe dello stesso
    # formato possono giocare la stessa sera: sono due post, non un doppione.
    torneo = meta.get("leg", "")
    return (f"{draft.kind}:{scope}:{meta.get('format', '')}"
            + (f":{torneo}" if torneo else ""))


def already_published(cfg: Config, key: str) -> dict | None:
    path = ledger_path(cfg)
    if not path.exists():
        return None
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("dedupe_key") == key and entry.get("status") == "published":
            return entry
    return None


def record(cfg: Config, entry: dict) -> None:
    with ledger_path(cfg).open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(entry, ensure_ascii=False) + "\n")


def save_draft_files(cfg: Config, draft: PostDraft) -> Path:
    """Salva caption e metadati accanto ai PNG: e' l'anteprima ispezionabile."""
    out_dir = cfg.resolve_path(cfg.get("render.output_dir", "out"))
    stem = Path(draft.images[0]).stem
    (out_dir / f"{stem}.caption.txt").write_text(draft.caption, encoding="utf-8")
    meta_path = out_dir / f"{stem}.json"
    meta_path.write_text(
        json.dumps(
            {"kind": draft.kind, "images": draft.images, "caption": draft.caption,
             "meta": draft.meta, "dedupe_key": dedupe_key(draft)},
            ensure_ascii=False, indent=2,
        ),
        encoding="utf-8",
    )
    return meta_path


def publish_draft(cfg: Config, draft: PostDraft, *, dry_run: bool = False,
                  force: bool = False) -> dict:
    """Pubblica un draft. In dry-run si ferma prima di toccare la rete."""
    save_draft_files(cfg, draft)
    key = dedupe_key(draft)
    entry = {
        "ts": datetime.now(UTC).isoformat(),
        "kind": draft.kind,
        "dedupe_key": key,
        "images": draft.images,
        "meta": draft.meta,
        "caption_chars": len(draft.caption),
    }

    if dry_run:
        entry["status"] = "dry-run"
        record(cfg, entry)
        return entry

    if not cfg.get("instagram.enabled", True) or not cfg.get("instagram.publish_enabled", True):
        entry["status"] = "skipped"
        entry["reason"] = "publish disabilitato in configurazione (instagram.publish_enabled)"
        record(cfg, entry)
        return entry

    previous = None if force else already_published(cfg, key)
    if previous:
        entry["status"] = "skipped"
        entry["reason"] = f"gia' pubblicato il {previous['ts']} (post {previous.get('post_id')})"
        entry["post_id"] = previous.get("post_id")
        record(cfg, entry)
        return entry

    try:
        client = InstagramClient(cfg)
        urls = upload_all(cfg, [Path(p) for p in draft.images])
        entry["image_urls"] = urls
        post_id = client.publish_post(urls, draft.caption)
    except PublishError as exc:
        entry["status"] = "error"
        entry["error"] = str(exc)
        record(cfg, entry)
        raise

    entry["status"] = "published"
    entry["post_id"] = post_id
    entry["permalink"] = client.permalink(post_id)
    record(cfg, entry)
    return entry
