"""Caricamento configurazione.

config/config.toml (versionato, senza segreti)
  + config/config.local.toml (git-ignored, override locali)
  + risoluzione di ${VAR} dalle variabili d'ambiente e da .env
"""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path
from typing import Any

from .errors import ConfigError

ENV_RE = re.compile(r"\$\{([A-Z0-9_]+)\}")
DEFAULT_CONFIG = Path("config/config.toml")
LOCAL_CONFIG = Path("config/config.local.toml")


def project_root() -> Path:
    """Radice del repo: risalita da questo file (src/moma_social/config.py)."""
    return Path(__file__).resolve().parents[2]


def load_dotenv(path: Path | None = None) -> None:
    """Carica un .env senza dipendenze esterne. Non sovrascrive l'ambiente."""
    env_file = path or project_root() / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("'\""))


def _expand(value: Any, mancanti: set[str] | None = None) -> Any:
    """Sostituisce ${VAR} ricorsivamente. Una var mancante diventa stringa vuota.

    I nomi rimasti vuoti finiscono in `mancanti`: una chiave assente non e' un
    errore (di Canva o di S3 se ne fa a meno), ma su un runner senza .env
    diventa un header vuoto e un 401 che non nomina la sua causa. Chi chiama
    decide se e' il caso di dirlo.
    """
    if isinstance(value, str):
        def sostituisci(m: re.Match) -> str:
            trovato = os.environ.get(m.group(1), "")
            if not trovato and mancanti is not None:
                mancanti.add(m.group(1))
            return trovato
        return ENV_RE.sub(sostituisci, value)
    if isinstance(value, dict):
        return {k: _expand(v, mancanti) for k, v in value.items()}
    if isinstance(value, list):
        return [_expand(v, mancanti) for v in value]
    return value


def _deep_merge(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


class Config:
    """Accesso per path puntato: cfg.get('instagram.ig_user_id')."""

    def __init__(self, data: dict, path: Path | None = None,
                 mancanti: set[str] | None = None):
        self.data = data
        self.path = path
        self.root = project_root()
        # Variabili d'ambiente citate nel config e rimaste vuote.
        self.env_mancanti = sorted(mancanti or ())

    # -- lettura ---------------------------------------------------------
    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self.data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def require(self, dotted: str) -> Any:
        value = self.get(dotted)
        if value in (None, "", [], {}):
            raise ConfigError(
                f"Configurazione mancante: '{dotted}'. "
                f"Impostala in {self.path or DEFAULT_CONFIG} o via variabile d'ambiente."
            )
        return value

    def section(self, dotted: str) -> dict:
        value = self.get(dotted, {})
        return value if isinstance(value, dict) else {}

    def resolve_path(self, value: str) -> Path:
        """Path relativo alla radice del progetto, assoluto se gia' tale."""
        candidate = Path(value)
        return candidate if candidate.is_absolute() else self.root / candidate

    @property
    def timezone(self) -> str:
        return self.get("org.timezone", "Europe/Rome")


def load(path: str | Path | None = None) -> Config:
    root = project_root()
    main = Path(path) if path else root / DEFAULT_CONFIG
    if not main.is_absolute():
        main = root / main
    if not main.exists():
        raise ConfigError(f"File di configurazione non trovato: {main}")

    load_dotenv()
    data = tomllib.loads(main.read_text(encoding="utf-8"))

    local = root / LOCAL_CONFIG
    if local.exists():
        data = _deep_merge(data, tomllib.loads(local.read_text(encoding="utf-8")))

    mancanti: set[str] = set()
    return Config(_expand(data, mancanti), main, mancanti)
