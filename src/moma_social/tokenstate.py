"""Da quanto tempo e' in giro il token Instagram.

Su Instagram Login non esiste `debug_token`: Meta dice solo se il token apre
ancora l'account, mai quanta vita gli resti. Il conto quindi lo teniamo noi.

Non serve pero' che qualcuno si ricordi di annotare la data del rinnovo: il
token cambia, e basta accorgersene. Di ogni token si tiene un'impronta e il
giorno in cui l'abbiamo visto per la prima volta; quando l'impronta cambia,
l'orologio riparte da capo.

Nel file non finisce il token ma un pezzo del suo SHA-256. Da li' non si
risale al token - e' un digest, non una cifratura - e serve solo a rispondere
"e' lo stesso di ieri?".
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
from pathlib import Path

# Quanto dura un token lungo di Instagram, per contratto di Meta.
DURATA_GIORNI = 60
LUNGHEZZA_IMPRONTA = 16


def impronta(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:LUNGHEZZA_IMPRONTA]


def _leggi(path: Path) -> dict:
    try:
        dati = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return dati if isinstance(dati, dict) else {}


def aggiorna(path: Path, token: str, oggi: dt.date | None = None) -> dict:
    """Registra il token e dice quanti giorni gli restano.

    `nuovo` distingue il primo avvistamento dai successivi: al primo giro su
    un token gia' vecchio il conto parte da oggi, quindi la stima e'
    ottimistica e chi legge deve poterlo sapere.
    """
    oggi = oggi or dt.date.today()
    corrente = impronta(token)
    dati = _leggi(path)

    if dati.get("impronta") != corrente:
        dati = {"impronta": corrente, "visto_il": oggi.isoformat()}
        nuovo = True
    else:
        nuovo = False

    try:
        visto = dt.date.fromisoformat(dati["visto_il"])
    except (KeyError, ValueError):
        visto = oggi
        dati["visto_il"] = oggi.isoformat()
        nuovo = True

    # Un orologio che va indietro (data del runner sballata, file da un'altra
    # macchina) non deve produrre una vita residua piu' lunga del contratto.
    vissuti = max(0, (oggi - visto).days)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(dati, indent=1) + "\n", encoding="utf-8")

    return {
        "impronta": corrente,
        "visto_il": dati["visto_il"],
        "nuovo": nuovo,
        "giorni_di_vita": vissuti,
        "giorni_rimasti": DURATA_GIORNI - vissuti,
        "scadenza": (visto + dt.timedelta(days=DURATA_GIORNI)).isoformat(),
    }
