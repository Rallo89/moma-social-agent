"""Il conto alla rovescia del token Instagram.

Meta non lo dice, quindi lo teniamo noi: questi test sono l'unica prova che il
promemoria arrivi prima della scadenza e non dopo.
"""

import datetime as dt
import json

from moma_social import tokenstate


def test_primo_avvistamento_fa_partire_il_conto(tmp_path):
    stato = tokenstate.aggiorna(tmp_path / "token.json", "IGQ-abc",
                                dt.date(2026, 9, 15))
    assert stato["nuovo"]
    assert stato["giorni_rimasti"] == 60
    assert stato["scadenza"] == "2026-11-14"


def test_lo_stesso_token_invecchia(tmp_path):
    path = tmp_path / "token.json"
    tokenstate.aggiorna(path, "IGQ-abc", dt.date(2026, 9, 15))
    stato = tokenstate.aggiorna(path, "IGQ-abc", dt.date(2026, 11, 7))
    assert not stato["nuovo"]
    assert stato["giorni_rimasti"] == 7
    assert stato["scadenza"] == "2026-11-14"


def test_un_token_nuovo_azzera_il_conto(tmp_path):
    """Il rinnovo non va annotato a mano: si vede che il token e' cambiato."""
    path = tmp_path / "token.json"
    tokenstate.aggiorna(path, "IGQ-vecchio", dt.date(2026, 9, 15))
    stato = tokenstate.aggiorna(path, "IGQ-nuovo", dt.date(2026, 11, 7))
    assert stato["nuovo"]
    assert stato["giorni_rimasti"] == 60


def test_il_token_non_finisce_nel_file(tmp_path):
    """Il file e' versionato: dentro ci va un digest, non il segreto."""
    path = tmp_path / "token.json"
    tokenstate.aggiorna(path, "IGQ-segretissimo", dt.date(2026, 9, 15))
    testo = path.read_text(encoding="utf-8")
    assert "IGQ-segretissimo" not in testo
    assert json.loads(testo)["impronta"] == tokenstate.impronta("IGQ-segretissimo")


def test_un_file_rovinato_non_blocca_il_controllo(tmp_path):
    """Meglio un conto che riparte che un controllo che va in errore."""
    path = tmp_path / "token.json"
    path.write_text("{ non json", encoding="utf-8")
    stato = tokenstate.aggiorna(path, "IGQ-abc", dt.date(2026, 9, 15))
    assert stato["nuovo"] and stato["giorni_rimasti"] == 60


def test_una_data_futura_nel_file_non_allunga_la_vita(tmp_path):
    """Orologio del runner sballato: non deve regalare giorni che non ci sono."""
    path = tmp_path / "token.json"
    path.write_text(json.dumps({"impronta": tokenstate.impronta("IGQ-abc"),
                                "visto_il": "2026-12-01"}), encoding="utf-8")
    stato = tokenstate.aggiorna(path, "IGQ-abc", dt.date(2026, 9, 15))
    assert stato["giorni_rimasti"] == 60
