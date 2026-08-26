"""Hosting delle immagini.

La Content Publishing API di Instagram non accetta upload binari: scarica
l'immagine da un URL pubblico. I PNG generati vanno quindi esposti su HTTP
prima della pubblicazione. Tre backend, uno solo attivo per volta.
"""

from __future__ import annotations

import mimetypes
from datetime import UTC, datetime
from pathlib import Path

import requests

from .config import Config
from .errors import ConfigError, PublishError

TIMEOUT = 60


def _key_for(prefix: str, path: Path) -> str:
    stamp = datetime.now(UTC).strftime("%Y/%m/%d")
    return f"{prefix.strip('/')}/{stamp}/{path.name}".lstrip("/")


def _upload_s3(cfg: Config, path: Path) -> str:
    try:
        import boto3
    except ImportError as exc:  # pragma: no cover
        raise ConfigError("backend media 's3' richiede boto3: pip install '.[s3]'") from exc

    section = cfg.section("media.s3")
    bucket = section.get("bucket")
    if not bucket:
        raise ConfigError("media.s3.bucket non configurato (variabile MEDIA_BUCKET)")

    client_args = {}
    if section.get("region"):
        client_args["region_name"] = section["region"]
    if section.get("endpoint_url"):
        client_args["endpoint_url"] = section["endpoint_url"]
    client = boto3.client("s3", **client_args)

    key = _key_for(section.get("prefix", ""), path)
    extra = {"ContentType": mimetypes.guess_type(path.name)[0] or "image/png"}
    if section.get("acl"):
        extra["ACL"] = section["acl"]
    try:
        client.upload_file(str(path), bucket, key, ExtraArgs=extra)
    except Exception as exc:  # noqa: BLE001 - boto3 solleva molte eccezioni diverse
        raise PublishError(f"Upload su S3 fallito ({bucket}/{key}): {exc}") from exc

    base = (section.get("public_base") or "").rstrip("/")
    if base:
        return f"{base}/{key}"
    region = section.get("region", "")
    host = f"s3.{region}.amazonaws.com" if region else "s3.amazonaws.com"
    return f"https://{bucket}.{host}/{key}"


def _upload_imgbb(cfg: Config, path: Path) -> str:
    api_key = cfg.get("media.imgbb.api_key")
    if not api_key:
        raise ConfigError("media.imgbb.api_key non configurato (variabile IMGBB_API_KEY)")
    data = {"key": api_key}
    if cfg.get("media.imgbb.expiration"):
        data["expiration"] = cfg.get("media.imgbb.expiration")
    try:
        response = requests.post(
            "https://api.imgbb.com/1/upload",
            data=data,
            files={"image": path.read_bytes()},
            timeout=TIMEOUT,
        )
        response.raise_for_status()
        return response.json()["data"]["url"]
    except (requests.RequestException, KeyError, ValueError) as exc:
        raise PublishError(f"Upload su imgbb fallito: {exc}") from exc


def upload(cfg: Config, path: Path) -> str:
    """Carica un PNG e restituisce l'URL pubblico da passare alla Graph API."""
    backend = cfg.get("media.backend", "none")
    if backend == "s3":
        return _upload_s3(cfg, path)
    if backend == "imgbb":
        return _upload_imgbb(cfg, path)
    if backend in ("none", "", "local"):
        raise ConfigError(
            "media.backend = 'none': le immagini restano locali e non possono essere "
            "pubblicate. Configura 's3' o 'imgbb', oppure lancia con --dry-run."
        )
    raise ConfigError(f"media.backend sconosciuto: {backend!r}")


def upload_all(cfg: Config, paths: list[Path]) -> list[str]:
    return [upload(cfg, Path(p)) for p in paths]
