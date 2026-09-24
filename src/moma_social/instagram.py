"""Client minimale della Instagram Content Publishing API.

Flusso singola immagine:   media -> media_publish
Flusso carosello:          media(is_carousel_item) x N -> media(CAROUSEL) -> media_publish

Il container va atteso: la API restituisce subito un id ma processa
l'immagine in modo asincrono, e un publish su container non FINISHED fallisce.

DUE PERCORSI, STESSE CHIAMATE
Meta espone la stessa API da due host, a seconda di come ci si autentica:

  graph.instagram.com   Instagram Login — si autentica l'account Instagram,
                        senza Pagina Facebook di mezzo
  graph.facebook.com    Facebook Login — richiede una Pagina Facebook
                        collegata all'account

I percorsi delle risorse sono gli stessi, cambia l'host: sta in
`instagram.api_host` e non tocca nient'altro di questo file.
"""

from __future__ import annotations

import json
import time

import requests

from .config import Config
from .errors import ConfigError, PublishError

TIMEOUT = 60
POLL_INTERVAL = 3
POLL_ATTEMPTS = 20
# L'app Instagram permette 20 slide, la Content Publishing API 10: pubblicando
# via API vale il secondo limite.
MAX_CAROUSEL = 10

# 36001/2207084 e' quello che Meta restituisce quando non riesce a *leggere*
# l'immagine. Dice "formato non supportato", ma lo dice anche quando il
# formato e' quello di sempre e a non aver funzionato e' stato lo scaricamento
# dall'hosting. Il 23 settembre ha fermato un carosello che un'ora dopo, con
# immagini identiche, e' passato: per questo si riprova una volta.
SCARICAMENTO_FALLITO = {2207084, 2207003, 2207052}
RIPROVA_DOPO = 15


class InstagramClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.ig_user_id = cfg.get("instagram.ig_user_id", "")
        self.token = cfg.get("instagram.access_token", "")
        self.version = cfg.get("instagram.api_version", "v21.0")
        self.host = cfg.get("instagram.api_host", "graph.facebook.com")
        # Profili da taggare come coautori del post (i "Collab" di Instagram).
        # Devono accettare l'invito perche' il post compaia anche da loro.
        # La API vuole gli username nudi: una "@" copiata dal profilo la
        # rifiuterebbe senza spiegare perche', quindi la togliamo qui.
        self.riprova_dopo = cfg.get("instagram.riprova_dopo_secondi",
                                    RIPROVA_DOPO)
        self.collaborators = [
            u.strip().lstrip("@")
            for u in (cfg.get("instagram.collaborators", []) or [])
            if u and u.strip().strip("@")
        ]

    # -- infrastruttura --------------------------------------------------
    @property
    def base(self) -> str:
        return f"https://{self.host}/{self.version}"

    @property
    def instagram_login(self) -> bool:
        return "graph.instagram.com" in self.host

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
                f"{error.get('message')}",
                code=error.get("code"), subcode=error.get("error_subcode"),
            )
        response.raise_for_status()
        return data

    # -- API -------------------------------------------------------------
    def check(self) -> dict:
        """Verifica credenziali e permessi: usata da `momasocial doctor`."""
        # `name` esiste solo sul percorso Facebook: chiederlo all'altro host
        # fa fallire tutta la chiamata per un campo che non ci serve.
        campi = ("id,username,followers_count" if self.instagram_login
                 else "id,username,name,followers_count")
        return self._get(self.ig_user_id, {"fields": campi})

    def _con_coautori(self, payload: dict) -> dict:
        """I coautori si dichiarano sul contenitore che porta la caption.

        Sulle singole slide di un carosello non hanno senso: il post e' uno.
        """
        if self.collaborators:
            payload = {**payload, "collaborators": json.dumps(self.collaborators)}
        return payload

    def create_item(self, image_url: str, *, caption: str = "",
                    is_carousel_item: bool = False) -> str:
        payload: dict = {"image_url": image_url}
        if is_carousel_item:
            payload["is_carousel_item"] = "true"
        else:
            if caption:
                payload["caption"] = caption
            payload = self._con_coautori(payload)
        return self._post(f"{self.ig_user_id}/media", payload)["id"]

    def create_carousel(self, children: list[str], caption: str) -> str:
        return self._post(
            f"{self.ig_user_id}/media",
            self._con_coautori({"media_type": "CAROUSEL",
                                "children": ",".join(children),
                                "caption": caption}),
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

    def _crea(self, azione):
        """Crea il contenitore, spiegando il caso dei coautori.

        `collaborators` e' un campo giovane: se questa versione della API o
        questo percorso di autenticazione non lo accetta, l'errore di Meta non
        dice da dove viene e si finisce a cercarlo nell'immagine o nella
        caption. Qui si nomina il parametro e la chiave da svuotare.
        """
        try:
            return azione()
        except PublishError as exc:
            if self.collaborators and "collaborator" in str(exc).lower():
                raise PublishError(
                    f"{exc}\n\nIl post chiedeva i coautori "
                    f"{', '.join(self.collaborators)}: e' il campo "
                    "`collaborators`, e Meta l'ha rifiutato. Svuota "
                    "instagram.collaborators in config/config.toml per "
                    "pubblicare senza, e segnalalo."
                ) from exc
            raise

    def _cosa_ce_a_quell_indirizzo(self, url: str) -> str:
        """Cosa trova chi scarica quell'URL, detto da noi e non da Meta.

        Meta, quando l'immagine non le torna, risponde sempre la stessa cosa:
        "formato non supportato". Non dice se ha scaricato un PNG che non le
        piace, una pagina di errore dell'hosting o niente del tutto — e sono
        tre guasti diversi, con tre rimedi diversi. Questo lo scarica e lo
        guarda.
        """
        try:
            risposta = requests.get(url, timeout=TIMEOUT, stream=True)
            inizio = next(risposta.iter_content(64), b"")
            tipo = risposta.headers.get("content-type", "?")
            peso = risposta.headers.get("content-length", "?")
            stato = risposta.status_code
            risposta.close()
        except requests.RequestException as exc:
            return f"non si scarica nemmeno da qui ({exc})"
        if inizio.startswith(b"\x89PNG"):
            contenuto = "un PNG"
        elif inizio.startswith(b"\xff\xd8\xff"):
            contenuto = "un JPEG"
        else:
            contenuto = f"non un'immagine ({inizio[:24]!r})"
        return f"HTTP {stato}, content-type {tipo}, {peso} byte, ed e' {contenuto}"

    def _contenitore(self, azione, url: str, quale: str):
        """Crea un contenitore, riprovando una volta se Meta non ha scaricato.

        Il secondo tentativo e' per il caso transitorio: l'hosting ha
        singhiozzato e Meta ha rinunciato. Se fallisce anche quello, l'errore
        smette di essere "formato non supportato" e diventa una frase che dice
        quale slide, a che indirizzo, e cosa c'e' davvero a quell'indirizzo.
        """
        try:
            return azione()
        except PublishError as exc:
            if exc.subcode in SCARICAMENTO_FALLITO:
                time.sleep(self.riprova_dopo)
                try:
                    return azione()
                except PublishError as riprovato:
                    exc = riprovato
            raise PublishError(
                f"{quale} rifiutata da Meta.\n{exc}\n"
                f"Immagine: {url}\n"
                f"A quell'indirizzo c'e': {self._cosa_ce_a_quell_indirizzo(url)}",
                code=exc.code, subcode=exc.subcode,
            ) from exc

    def publish_post(self, image_urls: list[str], caption: str) -> str:
        """Pubblica immagine singola o carosello. Restituisce l'id del post."""
        if not image_urls:
            raise PublishError("Nessuna immagine da pubblicare")
        if len(image_urls) > MAX_CAROUSEL:
            raise PublishError(
                f"Carosello di {len(image_urls)} slide: la Graph API ne accetta "
                f"al massimo {MAX_CAROUSEL}. Riduci posts.leg_results."
                f"max_carousel_slides o aumenta rows_per_slide."
            )
        if len(image_urls) == 1:
            container = self._crea(lambda: self._contenitore(
                lambda: self.create_item(image_urls[0], caption=caption),
                image_urls[0], "L'immagine"))
        else:
            children = []
            for numero, url in enumerate(image_urls, 1):
                child = self._contenitore(
                    lambda url=url: self.create_item(url, is_carousel_item=True),
                    url, f"La slide {numero} di {len(image_urls)}")
                self.wait_ready(child)
                children.append(child)
            container = self._crea(lambda: self.create_carousel(children, caption))
        self.wait_ready(container)
        return self.publish(container)
