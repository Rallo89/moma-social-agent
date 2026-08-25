import datetime as dt

import pytest

from mtg_social import cli
from mtg_social.errors import NoDataError


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
    from mtg_social.errors import ConfigError
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
