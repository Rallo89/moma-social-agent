"""Copertina della Pagina via Graph API, separata da Instagram.

Contratto verificato su developers.facebook.com/docs/graph-api/reference/page/
e page/photos/: upload non pubblicato, cover = ID numerico della foto.
La lettura successiva conferma l'applicazione prima di registrare il successo.
"""

from pathlib import Path

import requests

from .config import Config
from .errors import ConfigError, PublishError


class FacebookClient:
    def __init__(self, cfg: Config):
        self.page_id = str(cfg.require("facebook.page_id"))
        self.token = cfg.require("facebook.access_token")
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
            raise PublishError(
                f"Facebook API: HTTP {response.status_code}, codice {code}. "
                "Verificare token, ruoli e permessi della pagina; "
                "la copertina non risulta confermata.", code=code,
            )
        return data

    def page(self) -> dict:
        page = self._request("GET", "me", params={"fields": "id,name,cover"})
        if str(page.get("id")) != self.page_id:
            raise ConfigError("Il token Facebook non appartiene a FB_PAGE_ID")
        return page

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
        return isinstance(cover, dict) and str(cover.get("id", "")) == photo_id
