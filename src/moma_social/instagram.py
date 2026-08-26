"""Client minimale della Instagram Content Publishing API (Graph API).

Flusso singola immagine:   media -> media_publish
Flusso carosello:          media(is_carousel_item) x N -> media(CAROUSEL) -> media_publish

Il container va atteso: la Graph API restituisce subito un id ma processa
l'immagine in modo asincrono, e un publish su container non FINISHED fallisce.
"""

from __future__ import annotations

import time

import requests

from .config import Config
from .errors import ConfigError, PublishError

TIMEOUT = 60
POLL_INTERVAL = 3
POLL_ATTEMPTS = 20


class InstagramClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.ig_user_id = cfg.get("instagram.ig_user_id", "")
        self.token = cfg.get("instagram.access_token", "")
        self.version = cfg.get("instagram.api_version", "v21.0")

    # -- infrastruttura --------------------------------------------------
    @property
    def base(self) -> str:
        return f"https://graph.facebook.com/{self.version}"

    def _check_credentials(self) -> None:
        missing = [
            name for name, value in (
                ("instagram.ig_user_id (IG_USER_ID)", self.ig_user_id),
                ("instagram.access_token (IG_ACCESS_TOKEN)", self.token),
            ) if not value
        ]
        if missing:
            raise ConfigError("Credenziali Instagram mancanti: " + ", ".join(missing))

    def _post(self, path: str, payload: dict) -> dict:
        self._check_credentials()
        payload = {**payload, "access_token": self.token}
        try:
            response = requests.post(f"{self.base}/{path}", data=payload, timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise PublishError(f"Graph API irraggiungibile: {exc}") from exc
        return self._unwrap(response)

    def _get(self, path: str, params: dict) -> dict:
        self._check_credentials()
        params = {**params, "access_token": self.token}
        try:
            response = requests.get(f"{self.base}/{path}", params=params, timeout=TIMEOUT)
        except requests.RequestException as exc:
            raise PublishError(f"Graph API irraggiungibile: {exc}") from exc
        return self._unwrap(response)

    @staticmethod
    def _unwrap(response: requests.Response) -> dict:
        try:
            data = response.json()
        except ValueError:
            raise PublishError(
                f"Risposta non JSON da Graph API ({response.status_code}): "
                f"{response.text[:300]}"
            ) from None
        if "error" in data:
            error = data["error"]
            raise PublishError(
                f"Graph API error {error.get('code')}/{error.get('error_subcode', '-')}: "
                f"{error.get('message')}"
            )
        response.raise_for_status()
        return data

    # -- API -------------------------------------------------------------
    def check(self) -> dict:
        """Verifica credenziali e permessi: usata da `momasocial doctor`."""
        return self._get(self.ig_user_id, {"fields": "id,username,name,followers_count"})

    def create_item(self, image_url: str, *, caption: str = "",
                    is_carousel_item: bool = False) -> str:
        payload: dict = {"image_url": image_url}
        if is_carousel_item:
            payload["is_carousel_item"] = "true"
        elif caption:
            payload["caption"] = caption
        return self._post(f"{self.ig_user_id}/media", payload)["id"]

    def create_carousel(self, children: list[str], caption: str) -> str:
        return self._post(
            f"{self.ig_user_id}/media",
            {"media_type": "CAROUSEL", "children": ",".join(children), "caption": caption},
        )["id"]

    def wait_ready(self, container_id: str) -> None:
        for _ in range(POLL_ATTEMPTS):
            status = self._get(container_id, {"fields": "status_code,status"})
            code = status.get("status_code")
            if code == "FINISHED":
                return
            if code in ("ERROR", "EXPIRED"):
                raise PublishError(
                    f"Container {container_id} in stato {code}: {status.get('status')}"
                )
            time.sleep(POLL_INTERVAL)
        raise PublishError(
            f"Container {container_id} non pronto dopo "
            f"{POLL_ATTEMPTS * POLL_INTERVAL}s di attesa"
        )

    def permalink(self, media_id: str) -> str:
        """Il media id non e' lo shortcode: il link va chiesto alla API."""
        try:
            return self._get(media_id, {"fields": "permalink"}).get("permalink", "")
        except PublishError:
            return ""

    def publish(self, creation_id: str) -> str:
        return self._post(f"{self.ig_user_id}/media_publish",
                          {"creation_id": creation_id})["id"]

    def publish_post(self, image_urls: list[str], caption: str) -> str:
        """Pubblica immagine singola o carosello. Restituisce l'id del post."""
        if not image_urls:
            raise PublishError("Nessuna immagine da pubblicare")
        if len(image_urls) == 1:
            container = self.create_item(image_urls[0], caption=caption)
        else:
            children = []
            for url in image_urls:
                child = self.create_item(url, is_carousel_item=True)
                self.wait_ready(child)
                children.append(child)
            container = self.create_carousel(children, caption)
        self.wait_ready(container)
        return self.publish(container)
