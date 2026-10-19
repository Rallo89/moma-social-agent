"""Copertina della Pagina via Graph API, separata da Instagram.

Contratto verificato su developers.facebook.com/docs/graph-api/reference/page/
e page/photos/: upload non pubblicato, cover = ID numerico della foto.
La lettura successiva conferma l'applicazione prima di registrare il successo.
"""

import hashlib
from pathlib import Path
from urllib.parse import urlsplit

import requests

from .config import Config
from .errors import ConfigError, PublishError


def _credential(value: str, name: str) -> str:
    value = str(value).strip().removeprefix(f"{name}=").strip().strip("\"'")
    if any(c.isspace() for c in value):
        raise ConfigError(f"{name} deve contenere un solo valore, senza spazi o righe aggiuntive")
    return value


def facebook_page_id(cfg: Config) -> str:
    value = _credential(cfg.get("facebook.page_id", ""), "FB_PAGE_ID")
    if value and not (value.isascii() and value.isdigit()):
        raise ConfigError("FB_PAGE_ID deve contenere soltanto l'ID numerico della pagina")
    return value


class FacebookClient:
    def __init__(self, cfg: Config):
        cfg.require("facebook.page_id")
        self.page_id = facebook_page_id(cfg)
        self.token = _credential(cfg.require("facebook.access_token"), "FB_PAGE_ACCESS_TOKEN")
        if not self.page_id or not self.token:
            raise ConfigError("FB_PAGE_ID e FB_PAGE_ACCESS_TOKEN non possono essere vuoti")
        self.base = f"https://graph.facebook.com/{cfg.get('facebook.api_version', 'v26.0')}"

    def _request(self, method: str, path: str, **kwargs) -> dict:
        try:
            response = requests.request(
                method, f"{self.base}/{path}",
                headers={"Authorization": f"Bearer {self.token}"}, timeout=60, **kwargs,
            )
        except requests.RequestException:
            # Non riportare URL/eccezioni requests: potrebbero contenere segreti.
            raise PublishError("Graph API Facebook irraggiungibile") from None
        try:
            data = response.json()
        except ValueError:
            raise PublishError("Risposta Facebook non JSON") from None
        if not isinstance(data, dict):
            raise PublishError("Risposta Facebook inattesa")
        if not response.ok or "error" in data:
            error = data.get("error", {})
            code = error.get("code") if isinstance(error, dict) else None
            permission_hint = ""
            if (code == 283 and isinstance(error, dict)
                    and "pages_manage_metadata" in str(error.get("message", ""))):
                permission_hint = ("Manca pages_manage_metadata: aggiungerlo al caso d'uso "
                                   "della Pagina e rigenerare il token con questa autorizzazione. ")
            raise PublishError(
                f"Facebook API: HTTP {response.status_code}, codice {code}. "
                + permission_hint +
                "Verificare token, ruoli e permessi della pagina; "
                "la copertina non risulta confermata.", code=code,
            )
        return data

    def page(self) -> dict:
        page = self._request("GET", "me", params={"fields": "id,name,cover"})
        if str(page.get("id")) == self.page_id:
            return page
        # Un token utente puo' elencare piu' pagine: scegliamo solo l'ID configurato.
        # Il token derivato resta in memoria e non finisce nel registro o nei log.
        original_id = str(page.get("id", ""))
        params = {"fields": "id,access_token", "limit": 100}
        seen = set()
        try:
            while True:
                accounts = self._request("GET", "me/accounts", params=params)
                selected = next((p for p in accounts.get("data", [])
                                 if str(p.get("id")) == self.page_id), None)
                if selected and selected.get("access_token"):
                    self.token = selected["access_token"]
                    page = self._request("GET", "me", params={"fields": "id,name,cover"})
                    if str(page.get("id")) == self.page_id:
                        return page
                    break
                after = accounts.get("paging", {}).get("cursors", {}).get("after")
                if not accounts.get("paging", {}).get("next") or not after or after in seen:
                    break
                seen.add(after)
                params = {**params, "after": after}
        except PublishError as exc:
            raise ConfigError(
                f"Il token Facebook non appartiene a FB_PAGE_ID={self.page_id}; "
                "impossibile ricavare il token della pagina. " + str(exc)
            ) from None
        actual_id = original_id if original_id.isascii() and original_id.isdigit() else "ignoto"
        raise ConfigError(f"Il token Facebook non appartiene a FB_PAGE_ID={self.page_id} "
                          f"(identita' iniziale {actual_id}). La pagina richiesta non e' "
                          "accessibile con questo token: verificare ID e autorizzazioni.")

    def upload_photo(self, path: Path) -> str:
        if not path.is_file():
            raise ConfigError(f"Copertina non trovata: {path}")
        if path.stat().st_size > 4 * 1024 * 1024:
            raise ConfigError("La copertina supera il limite Facebook di 4 MB")
        try:
            with path.open("rb") as handle:
                data = self._request(
                    "POST", f"{self.page_id}/photos", data={"published": "false"},
                    files={"source": (path.name, handle, "image/png")},
                )
        except OSError:
            raise ConfigError(f"Impossibile leggere la copertina: {path}") from None
        if not str(data.get("id", "")).isdigit():
            raise PublishError("Facebook non ha restituito l'ID della foto")
        return str(data["id"])

    def set_cover(self, photo_id: str) -> None:
        result = self._request("POST", self.page_id,
                               data={"cover": photo_id, "no_feed_story": "true"})
        if result.get("success") is not True:
            raise PublishError("Facebook non ha confermato l'aggiornamento della copertina")

    def verify_cover(self, photo_id: str) -> bool:
        cover = self.page().get("cover") or {}
        if not isinstance(cover, dict):
            return False
        current_id = str(cover.get("id") or cover.get("cover_id") or "")
        if current_id == photo_id:
            return True
        if not current_id:
            return False
        # Facebook puo' copiare la foto nell'album copertine assegnando un nuovo ID.
        # Verifichiamo i file alla stessa risoluzione, senza confronti approssimativi.
        try:
            expected = self._photo_sources(photo_id)
            current = self._photo_sources(current_id)
            sizes = expected.keys() & current.keys()
            if not sizes:
                return False
            size = max(sizes, key=lambda size: size[0] * size[1])
            return self._image_digest(expected[size]) == self._image_digest(current[size])
        except PublishError:
            return False

    def _photo_sources(self, photo_id: str) -> dict:
        data = self._request("GET", photo_id, params={"fields": "images"})
        return {(image["width"], image["height"]): image["source"]
                for image in data.get("images", [])
                if isinstance(image, dict) and isinstance(image.get("width"), int)
                and isinstance(image.get("height"), int)
                and image["width"] > 0 and image["height"] > 0 and image.get("source")}

    @staticmethod
    def _image_digest(url: str) -> str:
        parsed = urlsplit(url)
        host = parsed.hostname or ""
        if parsed.scheme != "https" or not host.endswith(".fbcdn.net"):
            raise PublishError("Sorgente foto Facebook non riconosciuta")
        try:
            # Nessun token viene inviato al CDN; i redirect non sono seguiti.
            with requests.get(url, timeout=30, stream=True, allow_redirects=False) as response:
                if not response.ok or not response.headers.get("Content-Type", "").startswith(
                    "image/"
                ):
                    raise PublishError("Impossibile leggere la foto Facebook per la verifica")
                digest = hashlib.sha256()
                size = 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > 4 * 1024 * 1024:
                        raise PublishError("Foto Facebook troppo grande per la verifica")
                    digest.update(chunk)
                if size == 0:
                    raise PublishError("Foto Facebook vuota durante la verifica")
                return digest.hexdigest()
        except requests.RequestException:
            raise PublishError("Download della foto Facebook non riuscito") from None
