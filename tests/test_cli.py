import datetime as dt

import pytest
import responses

from moma_social import cli
from moma_social.errors import NoDataError


@pytest.fixture(autouse=True)
def config_del_repo(monkeypatch, cfg):
    """La CLI ricarica la config da sola: le si passa quella dei test."""
    monkeypatch.setattr(cli.config, "load", lambda path=None: cfg)


def test_agenda(capsys):
    assert cli.main(["agenda", "--date", "2026-03-11"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "5 eventi" in out
    assert "Tappa 4 - Modern League" in out


def test_agenda_json(capsys):
    cli.main(["agenda", "--date", "2026-03-11", "--json"])
    assert '"format": "Modern"' in capsys.readouterr().out


def test_agenda_settimana_vuota(capsys):
    assert cli.main(["agenda", "--date", "2030-01-01"]) == cli.EXIT_NO_DATA


def test_no_data_esce_con_78(monkeypatch, capsys):
    monkeypatch.setitem(cli.PIPELINES, "weekly_calendar",
                        lambda *a, **k: (_ for _ in ()).throw(NoDataError("niente")))
    assert cli.main(["weekly"]) == cli.EXIT_NO_DATA
    assert "[skip]" in capsys.readouterr().err


def test_gate_ora_giusta(monkeypatch, capsys):
    monkeypatch.setattr(cli, "now", lambda tz: dt.datetime(2026, 3, 9, 10, 0))
    cli.main(["gate", "--hour", "10", "--weekday", "0"])
    assert "run=true" in capsys.readouterr().out


def test_gate_ora_sbagliata(monkeypatch, capsys):
    """Lo scatto UTC che a Roma non corrisponde all'orario voluto non pubblica."""
    monkeypatch.setattr(cli, "now", lambda tz: dt.datetime(2026, 3, 9, 9, 0))
    cli.main(["gate", "--hour", "10"])
    assert "run=false" in capsys.readouterr().out


def test_gate_giorno_sbagliato(monkeypatch, capsys):
    monkeypatch.setattr(cli, "now", lambda tz: dt.datetime(2026, 3, 10, 10, 0))
    cli.main(["gate", "--hour", "10", "--weekday", "0"])
    assert "run=false" in capsys.readouterr().out


def test_gate_scrive_github_output(monkeypatch, tmp_path, capsys):
    output = tmp_path / "gh_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setattr(cli, "now", lambda tz: dt.datetime(2026, 3, 9, 10, 0))
    cli.main(["gate", "--hour", "10"])
    assert "run=true" in output.read_text(encoding="utf-8")


def test_errore_di_configurazione_esce_con_1(monkeypatch, capsys):
    from moma_social.errors import ConfigError
    monkeypatch.setitem(cli.PIPELINES, "weekly_calendar",
                        lambda *a, **k: (_ for _ in ()).throw(ConfigError("manca X")))
    assert cli.main(["weekly"]) == cli.EXIT_ERROR
    assert "manca X" in capsys.readouterr().err


def test_doctor_distingue_warning_da_errori(cfg, capsys):
    """Sorgente senza dati = warning; credenziali mancanti = errore."""
    cfg.data["sources"]["events"]["url"] = "data/samples/events.json"
    cfg.data["instagram"]["ig_user_id"] = ""
    cfg.data["instagram"]["access_token"] = ""
    cli.main(["doctor"])
    out = capsys.readouterr().out
    assert "⚠️" in out          # settimana corrente senza eventi di esempio
    assert "❌" in out          # credenziali assenti


@responses.activate
def test_schema_elenca_tabelle_e_colonne(monkeypatch, capsys):
    """La radice PostgREST descrive lo schema: e' li' che stanno i nomi veri."""
    monkeypatch.setenv("SUPABASE_KEY", "CHIAVE")
    responses.get("https://abc.supabase.co/rest/v1/", json={"definitions": {
        "eventi": {"properties": {"data": {}, "titolo": {}, "formato": {}}},
        "risultati": {"properties": {"posizione": {}, "giocatore": {}}},
    }})
    cli.main(["schema", "--url", "https://abc.supabase.co/rest/v1/"])
    out = capsys.readouterr().out
    assert "eventi" in out and "titolo" in out
    assert "risultati" in out and "giocatore" in out
    assert "2 tabelle" in out


def test_schema_senza_chiave(capsys):
    assert cli.main(["schema", "--url", "https://abc.supabase.co/rest/v1/",
                     "--key", ""]) == cli.EXIT_ERROR


def test_doctor_sonda_lultima_giornata_non_ieri(cfg, capsys):
    """Sondare 'ieri' segnalerebbe un guasto ogni giorno in cui non si gioca."""
    import datetime as d

    from moma_social.cli import _ultima_giornata

    giorno, motivo = _ultima_giornata(cfg, d.date(2026, 3, 16))
    assert giorno == d.date(2026, 3, 15)          # domenica, ultimo evento in calendario
    assert "calendario" in motivo


def test_doctor_sceglie_un_formato_esistente(cfg):
    """Meglio provare un formato che c'e' davvero che indovinarne uno."""
    import datetime as d

    from moma_social.cli import _formato_da_provare

    assert _formato_da_provare(cfg, d.date(2026, 3, 16)) in (
        "Commander", "Modern", "Pioneer", "Limited", "Pauper",
    )


def test_doctor_senza_eventi_ripiega_su_ieri(cfg):
    import datetime as d

    from moma_social.cli import _ultima_giornata

    giorno, motivo = _ultima_giornata(cfg, d.date(2030, 1, 10))
    assert "ieri" in motivo


def test_settimana_genera_un_post_per_giornata(cfg, capsys):
    """Nei dati di esempio si gioca il 11 e il 12 marzo: due post, non sette."""
    assert cli.main(["results", "--date", "2026-03-11", "--settimana",
                     "--no-publish", "--no-standings"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "Settimana 9 - 15 marzo" in out
    assert "3 post su 7 giornate" in out      # 11, 12 e 13 marzo
    assert "4 senza tappe" in out
    # Le giornate vuote dichiarano il perche': senza motivo non si distingue
    # "non si e' giocato" da "si e' giocato ma la vista non ha righe".
    assert "Nessun risultato per la tappa del 2026-03-09" in out


def test_settimana_senza_tappe(cfg, capsys):
    assert cli.main(["results", "--date", "2030-01-08", "--settimana",
                     "--no-publish"]) == cli.EXIT_NO_DATA
    assert "0 post su 7 giornate" in capsys.readouterr().out


def test_settimana_prosegue_dopo_una_giornata_fallita(cfg, monkeypatch, capsys):
    """Una sorgente giu' un giorno non deve far perdere gli altri sei."""
    import datetime as d

    from moma_social import pipelines
    from moma_social.errors import SourceError

    vero = pipelines.leg_results

    def _a_volte_rotta(cfg_, day=None, **kw):
        if day == d.date(2026, 3, 12):
            raise SourceError("endpoint irraggiungibile")
        return vero(cfg_, day, **kw)

    monkeypatch.setitem(cli.PIPELINES, "leg_results", _a_volte_rotta)
    esito = cli.main(["results", "--date", "2026-03-11", "--settimana",
                      "--no-publish", "--no-standings"])
    catturato = capsys.readouterr()
    assert esito == cli.EXIT_ERROR                    # la giornata persa si dichiara
    # Il fallimento si conta a parte: non deve travestirsi da giorno di riposo.
    assert "2 post su 7 giornate (4 senza tappe, 1 fallita)" in catturato.out
    assert "1 giornate fallite" in catturato.err
