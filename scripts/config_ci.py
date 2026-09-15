"""Scrive config/config.local.toml puntando alle sorgenti di esempio.

La CI deve poter dire se il rendering si e' rotto, e per farlo non ha bisogno
del database dell'associazione: con la chiave vera in mezzo ogni push
interrogherebbe la produzione, e senza la chiave la CI e' rossa per un motivo
che col codice non c'entra.

I file in data/samples/ usano i nomi canonici (`date`, `title`, ...), mentre
la vista Supabase usa quelli italiani: la mappa va quindi riportata
all'identita'. Non si scrive a mano - si deriva da config.toml, cosi' un campo
aggiunto domani alla mappa vera arriva qui da solo invece di sparire in
silenzio dalla card di prova.
"""

from __future__ import annotations

import sys
import tomllib
from pathlib import Path

RADICE = Path(__file__).resolve().parents[1]
CAMPIONI = {"events": "data/samples/events.json",
            "results": "data/samples/results.json",
            "standings": "data/samples/standings.json"}


def main() -> int:
    config = tomllib.loads((RADICE / "config/config.toml").read_text(encoding="utf-8"))
    righe = []
    for nome, campione in CAMPIONI.items():
        if not (RADICE / campione).exists():
            print(f"manca {campione}", file=sys.stderr)
            return 1
        righe += [f"[sources.{nome}]",
                  f'url  = "{campione}"',
                  'kind = "json"',
                  "",
                  f"[sources.{nome}.map]"]
        # Le intestazioni restano quelle di config.toml ma non vengono usate:
        # un path locale non passa dal ramo HTTP.
        mappa = config.get("sources", {}).get(nome, {}).get("map", {})
        righe += [f'{chiave} = "{chiave}"' for chiave in mappa]
        righe.append("")

    destinazione = RADICE / "config/config.local.toml"
    destinazione.write_text("\n".join(righe), encoding="utf-8")
    print(f"scritto {destinazione}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
