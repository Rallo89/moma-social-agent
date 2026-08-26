"""Collegamento a Canva: recupero degli sfondi via Connect API.

Perche' esiste: i template grafici vivono su Canva e devono finire come PNG in
templates/images/assets/. Questo modulo fa quel passaggio, senza che nessuno
debba scaricare e rinominare file a mano.

Perche' NON gira nei workflow schedulati: l'OAuth di Canva e' per utente, con
refresh token monouso a rotazione. In un cron, un refresh andato male rompe la
catena e richiede una riautorizzazione dal browser. Se succedesse di martedi',
il calendario del lunedi' successivo non deve fermarsi. Quindi `canva-sync` si
lancia a mano (o su schedule raro) e committa i PNG nel repo: i workflow di
pubblicazione leggono i file, non Canva.

Flusso:
    momasocial canva-auth     una volta sola, apre il browser e salva i token
    momasocial canva-sync     riesporta gli sfondi configurati
"""

from __future__ import annotations

import base64
import hashlib
import http.server
import json
import secrets
import threading
import time
import urllib.parse
import webbrowser
from dataclasses import dataclass
from pathlib import Path

import requests

from .config import Config
from .errors import ConfigError, MtgSocialError

AUTHORIZE_URL = "https://www.canva.com/api/oauth/authorize"
TOKEN_URL = "https://api.canva.com/rest/v1/oauth/token"
API_BASE = "https://api.canva.com/rest/v1"
# design:content:read serve per esportare, design:meta:read per leggere il
# titolo del design (compare nei log del sync).
SCOPES = ("design:content:read", "design:meta:read")
TIMEOUT = 60
POLL_INTERVAL = 2
POLL_ATTEMPTS = 60
# Canva rifiuta "localhost" come redirect: va usato l'indirizzo numerico.
REDIRECT_HOST = "127.0.0.1"


class CanvaError(MtgSocialError):
    """Errore nel dialogo con Canva."""


@dataclass
class AssetSpec:
    """Una riga di [[canva.assets]]: da quale design arriva quale file."""

    design_id: str
    target: str
    page: int = 1
    label: str = ""

    @property
    def name(self) -> str:
        return self.label or Path(self.target).name


# ── configurazione ──────────────────────────────────────────────────────────
def assets_from_config(cfg: Config) -> list[AssetSpec]:
    entries = cfg.get("canva.assets", []) or []
    specs = []
    for index, entry in enumerate(entries, start=1):
        missing = [k for k in ("design_id", "target") if not entry.get(k)]
        if missing:
            raise ConfigError(
                f"[[canva.assets]] #{index}: manca {', '.join(missing)}"
            )
        specs.append(
            AssetSpec(
                design_id=entry["design_id"],
                target=entry["target"],
                page=int(entry.get("page", 1)),
                label=entry.get("label", ""),
            )
        )
    if not specs:
        raise ConfigError(
            "Nessuno sfondo configurato: aggiungi almeno un blocco "
            "[[canva.assets]] in config/config.toml"
        )
    return specs


def token_path(cfg: Config) -> Path:
    return cfg.resolve_path(cfg.get("canva.token_file", "config/canva-tokens.json"))


# ── client ──────────────────────────────────────────────────────────────────
class CanvaClient:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.client_id = cfg.get("canva.client_id", "")
        self.client_secret = cfg.get("canva.client_secret", "")
        self.token_file = token_path(cfg)

    # -- credenziali -----------------------------------------------------
    def _require_client(self) -> None:
        missing = [
            name for name, value in (
                ("canva.client_id (CANVA_CLIENT_ID)", self.client_id),
                ("canva.client_secret (CANVA_CLIENT_SECRET)", self.client_secret),
            ) if not value
        ]
        if missing:
            raise ConfigError("Credenziali Canva mancanti: " + ", ".join(missing))

    @property
    def _basic_auth(self) -> str:
        raw = f"{self.client_id}:{self.client_secret}".encode()
        return "Basic " + base64.b64encode(raw).decode()

    # -- token -----------------------------------------------------------
    def load_tokens(self) -> dict:
        if not self.token_file.exists():
            raise ConfigError(
                f"Nessun token Canva in {self.token_file}. "
                "Esegui prima: momasocial canva-auth"
            )
        return json.loads(self.token_file.read_text(encoding="utf-8"))

    def save_tokens(self, payload: dict) -> None:
        """Salva subito i token: il refresh token e' monouso e a rotazione.

        Se si perde quello nuovo dopo aver speso il vecchio, la catena e'
        rotta e serve riautorizzare dal browser. Per questo la scrittura
        avviene prima di qualunque altra operazione, ed e' atomica.
        """
        self.token_file.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "access_token": payload["access_token"],
            "refresh_token": payload.get("refresh_token", ""),
            "expires_at": int(time.time()) + int(payload.get("expires_in", 0)),
            "scope": payload.get("scope", ""),
        }
        temporary = self.token_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(record, indent=2), encoding="utf-8")
        temporary.replace(self.token_file)
        self.token_file.chmod(0o600)

    def _token_request(self, data: dict) -> dict:
        self._require_client()
        try:
            response = requests.post(
                TOKEN_URL, data=data,
                headers={"Authorization": self._basic_auth},
                timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            raise CanvaError(f"Endpoint token Canva irraggiungibile: {exc}") from exc

        try:
            payload = response.json()
        except ValueError:
            raise CanvaError(
                f"Risposta non JSON dal token endpoint ({response.status_code}): "
                f"{response.text[:200]}"
            ) from None
        if "error" in payload:
            raise CanvaError(
                f"Canva OAuth: {payload['error']} — "
                f"{payload.get('error_description', 'nessun dettaglio')}"
            )
        response.raise_for_status()
        self.save_tokens(payload)
        return payload

    def exchange_code(self, code: str, verifier: str, redirect_uri: str) -> dict:
        return self._token_request({
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "redirect_uri": redirect_uri,
        })

    def refresh(self) -> str:
        tokens = self.load_tokens()
        if not tokens.get("refresh_token"):
            raise ConfigError(
                "Token Canva senza refresh_token: riesegui momasocial canva-auth"
            )
        payload = self._token_request({
            "grant_type": "refresh_token",
            "refresh_token": tokens["refresh_token"],
            "scope": " ".join(SCOPES),
        })
        return payload["access_token"]

    def access_token(self) -> str:
        """Token valido, rinnovato se scade entro un minuto."""
        tokens = self.load_tokens()
        if tokens.get("access_token") and tokens.get("expires_at", 0) - 60 > time.time():
            return tokens["access_token"]
        return self.refresh()

    # -- API -------------------------------------------------------------
    def _get(self, path: str) -> dict:
        return self._call("get", path)

    def _call(self, method: str, path: str, json_body: dict | None = None) -> dict:
        token = self.access_token()
        try:
            response = requests.request(
                method, f"{API_BASE}/{path.lstrip('/')}",
                headers={"Authorization": f"Bearer {token}"},
                json=json_body, timeout=TIMEOUT,
            )
        except requests.RequestException as exc:
            raise CanvaError(f"Canva API irraggiungibile: {exc}") from exc

        if response.status_code == 404:
            raise CanvaError(
                f"Risorsa non trovata su Canva: {path}. "
                "Controlla il design_id e che il design sia accessibile all'account autorizzato."
            )
        try:
            payload = response.json()
        except ValueError:
            raise CanvaError(
                f"Risposta non JSON da Canva ({response.status_code}): "
                f"{response.text[:200]}"
            ) from None
        if response.status_code >= 400:
            message = payload.get("message") or payload.get("error") or response.text[:200]
            raise CanvaError(f"Canva API {response.status_code}: {message}")
        return payload

    def design_title(self, design_id: str) -> str:
        try:
            return self._get(f"designs/{design_id}").get("design", {}).get("title", "")
        except CanvaError:
            return ""

    def export_png(self, design_id: str, quality: str = "regular") -> list[str]:
        """Avvia l'export, attende il job e restituisce gli URL delle pagine."""
        job = self._call("post", "exports", {
            "design_id": design_id,
            "format": {"type": "png", "export_quality": quality},
        }).get("job", {})

        job_id = job.get("id")
        if not job_id:
            raise CanvaError(f"Canva non ha restituito un job di export per {design_id}")

        for _ in range(POLL_ATTEMPTS):
            if job.get("status") == "success":
                urls = job.get("urls") or []
                if not urls:
                    raise CanvaError(f"Export {job_id} riuscito ma senza URL")
                return urls
            if job.get("status") == "failed":
                error = job.get("error", {})
                raise CanvaError(
                    f"Export fallito per {design_id}: "
                    f"{error.get('code', '')} {error.get('message', '')}".strip()
                )
            time.sleep(POLL_INTERVAL)
            job = self._get(f"exports/{job_id}").get("job", {})

        raise CanvaError(
            f"Export {job_id} non concluso dopo {POLL_ATTEMPTS * POLL_INTERVAL}s"
        )

    def download(self, url: str) -> bytes:
        """Scarica subito: gli URL di export scadono dopo 24 ore."""
        try:
            response = requests.get(url, timeout=TIMEOUT)
            response.raise_for_status()
            return response.content
        except requests.RequestException as exc:
            raise CanvaError(f"Download dell'export fallito: {exc}") from exc


# ── autorizzazione (una volta sola, dalla macchina di chi la esegue) ────────
def _pkce_pair() -> tuple[str, str]:
    """code_verifier e code_challenge SHA-256, come richiede Canva."""
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(64)).decode().rstrip("=")
    digest = hashlib.sha256(verifier.encode()).digest()
    challenge = base64.urlsafe_b64encode(digest).decode().rstrip("=")
    return verifier, challenge


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Riceve il redirect di Canva e mostra un esito leggibile nel browser."""

    result: dict = {}

    def do_GET(self):  # noqa: N802 - nome imposto da BaseHTTPRequestHandler
        query = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        _CallbackHandler.result = {k: v[0] for k, v in query.items()}
        ok = "code" in _CallbackHandler.result
        body = (
            "<h2>Autorizzazione completata</h2><p>Puoi chiudere questa scheda "
            "e tornare al terminale.</p>" if ok else
            f"<h2>Autorizzazione non riuscita</h2><pre>{_CallbackHandler.result}</pre>"
        )
        self.send_response(200 if ok else 400)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        self.wfile.write(f"<html><body style='font-family:sans-serif'>{body}</body></html>"
                         .encode())

    def log_message(self, *args):  # silenzia il log di default
        return


def authorize(cfg: Config, open_browser: bool = True, timeout: int = 300) -> str:
    """Flusso OAuth completo: restituisce il path del file token scritto."""
    client = CanvaClient(cfg)
    client._require_client()

    port = int(cfg.get("canva.redirect_port", 8721))
    redirect_uri = f"http://{REDIRECT_HOST}:{port}"
    verifier, challenge = _pkce_pair()
    state = secrets.token_urlsafe(16)

    url = AUTHORIZE_URL + "?" + urllib.parse.urlencode({
        "code_challenge": challenge,
        "code_challenge_method": "s256",
        "scope": " ".join(SCOPES),
        "response_type": "code",
        "client_id": client.client_id,
        "state": state,
        "redirect_uri": redirect_uri,
    })

    try:
        server = http.server.HTTPServer((REDIRECT_HOST, port), _CallbackHandler)
    except OSError as exc:
        raise CanvaError(
            f"Impossibile ascoltare su {redirect_uri}: {exc}. "
            "Cambia canva.redirect_port (e aggiorna il redirect URL su Canva)."
        ) from exc

    _CallbackHandler.result = {}
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    print(f"Apri questo indirizzo e autorizza l'integrazione:\n\n{url}\n")
    if open_browser:
        webbrowser.open(url)

    thread.join(timeout)
    server.server_close()

    result = _CallbackHandler.result
    if not result:
        raise CanvaError(f"Nessuna risposta da Canva entro {timeout}s: riprova.")
    if result.get("state") != state:
        raise CanvaError("Parametro `state` non corrispondente: autorizzazione annullata.")
    if "code" not in result:
        raise CanvaError(
            f"Canva ha negato l'autorizzazione: {result.get('error', '?')} — "
            f"{result.get('error_description', '')}"
        )

    client.exchange_code(result["code"], verifier, redirect_uri)
    return str(client.token_file)


# ── sincronizzazione degli sfondi ───────────────────────────────────────────
def sync(cfg: Config, only: str = "", check: bool = False) -> list[dict]:
    """Riesporta gli sfondi configurati. `check` non scrive nulla su disco."""
    client = CanvaClient(cfg)
    quality = cfg.get("canva.export_quality", "regular")
    specs = assets_from_config(cfg)
    if only:
        specs = [s for s in specs if only in (s.name, s.target, s.design_id)]
        if not specs:
            raise ConfigError(f"Nessuno sfondo configurato corrisponde a '{only}'")

    report = []
    for spec in specs:
        urls = client.export_png(spec.design_id, quality)
        if spec.page > len(urls):
            raise CanvaError(
                f"{spec.name}: richiesta pagina {spec.page} ma il design "
                f"{spec.design_id} ne ha {len(urls)}"
            )
        content = client.download(urls[spec.page - 1])

        target = cfg.resolve_path(spec.target)
        previous = target.read_bytes() if target.exists() else b""
        changed = hashlib.sha256(content).digest() != hashlib.sha256(previous).digest()

        if changed and not check:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content)

        report.append({
            "nome": spec.name,
            "design_id": spec.design_id,
            "pagina": spec.page,
            "file": spec.target,
            "stato": ("da aggiornare" if check else "aggiornato") if changed
                     else "invariato",
            "byte": len(content),
        })
    return report
