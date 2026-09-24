import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from moma_social import config  # noqa: E402


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """Config reale del repo, ma isolata: niente rete, niente file del progetto.

    Le sorgenti puntano ai dati di esempio invece che al Supabase reale: i test
    devono girare identici in CI, offline e senza credenziali. I nomi dei campi
    nei file di esempio coincidono gia' con quelli del modello, quindi non
    serve nessuna mappatura.
    """
    monkeypatch.setattr(config, "project_root", lambda: ROOT)
    loaded = config.load()
    loaded.data["render"]["output_dir"] = str(tmp_path / "out")
    loaded.data["publish"]["ledger"] = str(tmp_path / "published.jsonl")
    # Il conto dei giorni del token scrive su file: fuori da tmp_path
    # sporcherebbe lo stato vero del repo a ogni giro di test.
    loaded.data["instagram"]["token_state"] = str(tmp_path / "token.json")
    # La pausa fra i due tentativi di pubblicazione non va aspettata davvero.
    loaded.data["instagram"]["riprova_dopo_secondi"] = 0
    for nome in ("events", "results", "standings"):
        loaded.data["sources"][nome] = {
            "url": f"data/samples/{nome}.json",
            "kind": "auto",
        }
    return loaded


@pytest.fixture
def sample_dir(tmp_path):
    target = tmp_path / "data"
    shutil.copytree(ROOT / "data" / "samples", target)
    return target
