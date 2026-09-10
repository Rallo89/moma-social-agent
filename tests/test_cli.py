import datetime as dt

import pytest
import responses

from moma_social import cli, pipelines
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
    monkeypatch.setitem(pipelines.PIPELINES, "weekly_calendar",
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
    monkeypatch.setitem(pipelines.PIPELINES, "weekly_calendar",
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

    from moma_social.errors import SourceError

    vero = pipelines.leg_results_batch

    def _a_volte_rotta(cfg_, day=None, **kw):
        if day == d.date(2026, 3, 12):
            raise SourceError("endpoint irraggiungibile")
        return vero(cfg_, day, **kw)

    monkeypatch.setitem(pipelines.PIPELINES_MULTI, "leg_results", _a_volte_rotta)
    esito = cli.main(["results", "--date", "2026-03-11", "--settimana",
                      "--no-publish", "--no-standings"])
    catturato = capsys.readouterr()
    assert esito == cli.EXIT_ERROR                    # la giornata persa si dichiara
    # Il fallimento si conta a parte: non deve travestirsi da giorno di riposo.
    assert "2 post su 7 giornate (4 senza tappe, 1 fallita)" in catturato.out
    assert "1 giornate fallite" in catturato.err


def test_doctor_sonda_la_classifica_con_la_lega_della_tappa(cfg):
    """Sondare per solo formato mescolerebbe le stagioni e darebbe rosso."""
    import datetime as d

    formato, lega, etichetta = cli._classifica_da_provare(
        cfg, d.date(2026, 3, 15), d.date(2026, 3, 13))
    assert formato == "Pauper"
    assert lega == "lega-pauper-2026"        # ereditata dalla tappa
    assert "lega della tappa" in etichetta


def test_doctor_senza_tappe_ricade_sul_formato(cfg):
    import datetime as d

    formato, lega, etichetta = cli._classifica_da_provare(
        cfg, d.date(2030, 1, 10), d.date(2030, 1, 9))
    assert lega == ""
    assert "nessuna lega" in etichetta
    assert formato


def test_agenda_mostra_il_titolo_della_card_e_la_quota(cfg, capsys, monkeypatch):
    """L'agenda anticipa la grafica: se sbaglia qui, sbaglia anche sulla card."""
    import datetime as d

    from moma_social import repos
    from moma_social.models import Event

    def eventi(cfg_, start, end):
        return [Event(date=d.date(2026, 9, 17), format="Modern",
                      title="Modern Fall tappa 2", league="Modern Fall 2026",
                      stage="2", venue="Uno Critico", entry_fee="10.00")]

    monkeypatch.setattr(repos, "fetch_events", eventi)
    assert cli.main(["agenda", "--date", "2026-09-17"]) == cli.EXIT_OK
    out = capsys.readouterr().out
    assert "Modern Fall 2026 · Tappa 2" in out    # non il nome grezzo
    assert "10 €" in out                          # non "10.00"


def test_media_test_riconosce_un_hosting_che_non_serve_immagini(cfg, monkeypatch,
                                                                capsys, tmp_path):
    """Un 200 che non e' un'immagine e' quasi sempre una pagina di login."""
    from moma_social import cli as modulo

    png = tmp_path / "slide.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 100)
    monkeypatch.setattr("moma_social.uploader.upload",
                        lambda cfg_, path: "https://esempio.invalid/slide.png")

    class Risposta:
        status_code = 200
        headers = {"Content-Type": "text/html", "Content-Length": "512"}

    monkeypatch.setattr("requests.get", lambda *a, **k: Risposta())
    esito = modulo.main(["media-test", "--file", str(png)])
    assert esito == cli.EXIT_ERROR
    assert "Content-Type" in capsys.readouterr().err


def test_media_test_promuove_un_hosting_corretto(cfg, monkeypatch, capsys, tmp_path):
    from moma_social import cli as modulo

    png = tmp_path / "slide.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\n" + b"0" * 100)
    monkeypatch.setattr("moma_social.uploader.upload",
                        lambda cfg_, path: "https://cdn.esempio.invalid/slide.png")

    class Risposta:
        status_code = 200
        headers = {"Content-Type": "image/png", "Content-Length": "108"}

    monkeypatch.setattr("requests.get", lambda *a, **k: Risposta())
    assert modulo.main(["media-test", "--file", str(png)]) == cli.EXIT_OK
    assert "Instagram riuscirebbe" in capsys.readouterr().out


def test_doctor_non_promuove_s3_senza_boto3(cfg, monkeypatch):
    """Una spia verde che mente e' peggio di nessuna spia."""
    import importlib.util

    from moma_social.errors import ConfigError

    cfg.data["media"]["backend"] = "s3"
    cfg.data["media"]["s3"]["bucket"] = "moma-social"
    vero = importlib.util.find_spec
    monkeypatch.setattr(importlib.util, "find_spec",
                        lambda nome, *a: None if nome == "boto3" else vero(nome, *a))
    with pytest.raises(ConfigError, match="boto3"):
        cli._check_media(cfg, "s3")


BASE_FB = "https://graph.facebook.com/v21.0"


def _token_lungo():
    responses.add(responses.GET, f"{BASE_FB}/oauth/access_token",
                  json={"access_token": "EAAlungo", "expires_in": 5184000})


@responses.activate
def test_ig_setup_stampa_i_due_valori(cfg, capsys):
    _token_lungo()
    responses.add(responses.GET, f"{BASE_FB}/me/accounts", json={"data": [
        {"id": "10", "name": "Modena Magic",
         "instagram_business_account": {"id": "1784", "username": "modenamagic"}},
    ]})
    esito = cli.main(["ig-setup", "--host", "graph.facebook.com",
                      "--token", "breve", "--app-id", "1", "--app-secret", "2"])
    out = capsys.readouterr().out
    assert esito == cli.EXIT_OK
    assert "IG_USER_ID=1784" in out
    assert "IG_ACCESS_TOKEN=EAAlungo" in out
    assert "@modenamagic" in out


@responses.activate
def test_ig_setup_spiega_la_pagina_senza_instagram(cfg, capsys):
    """L'errore piu' probabile: Pagina c'e', collegamento no."""
    _token_lungo()
    responses.add(responses.GET, f"{BASE_FB}/me/accounts",
                  json={"data": [{"id": "10", "name": "Modena Magic"}]})
    assert cli.main(["ig-setup", "--host", "graph.facebook.com",
                     "--token", "breve", "--app-id", "1", "--app-secret", "2"]) == cli.EXIT_ERROR
    assert "professionale collegato" in capsys.readouterr().err


@responses.activate
def test_ig_setup_chiede_quale_pagina(cfg, capsys):
    _token_lungo()
    responses.add(responses.GET, f"{BASE_FB}/me/accounts", json={"data": [
        {"id": "10", "name": "Modena Magic",
         "instagram_business_account": {"id": "1", "username": "a"}},
        {"id": "20", "name": "Uno Critico",
         "instagram_business_account": {"id": "2", "username": "b"}},
    ]})
    assert cli.main(["ig-setup", "--host", "graph.facebook.com",
                     "--token", "breve", "--app-id", "1", "--app-secret", "2"]) == cli.EXIT_ERROR
    assert "--page" in capsys.readouterr().err


@responses.activate
def test_ig_setup_riporta_l_errore_di_meta(cfg, capsys):
    responses.add(responses.GET, f"{BASE_FB}/oauth/access_token", json={
        "error": {"message": "Invalid appsecret", "code": 101}})
    esito = cli.main(["ig-setup", "--host", "graph.facebook.com", "--token",
                      "breve", "--app-id", "1", "--app-secret", "sbagliato"])
    assert esito == cli.EXIT_ERROR
    err = capsys.readouterr().err
    assert "Scambio del token" in err and "Invalid appsecret" in err


BASE_IG = "https://graph.instagram.com"


@responses.activate
def test_ig_setup_instagram_login_non_passa_dalla_pagina(cfg, capsys):
    """Due chiamate sole: scambio del token e lettura dell'account."""
    responses.add(responses.GET, f"{BASE_IG}/access_token",
                  json={"access_token": "IGQlungo", "expires_in": 5184000})
    responses.add(responses.GET, f"{BASE_IG}/v21.0/me",
                  json={"id": "17841400000000000", "username": "modenamagic"})
    esito = cli.main(["ig-setup", "--token", "breve", "--app-secret", "segreto"])
    out = capsys.readouterr().out
    assert esito == cli.EXIT_OK
    assert "IG_USER_ID=17841400000000000" in out
    assert "IG_ACCESS_TOKEN=IGQlungo" in out
    assert "@modenamagic" in out
    # Nessuna chiamata a Facebook: e' il punto di questo percorso.
    assert all("facebook.com" not in c.request.url for c in responses.calls)


@responses.activate
def test_ig_setup_instagram_riporta_l_errore_nel_formato_di_instagram(cfg, capsys):
    """graph.instagram.com non usa la busta "error" di Facebook."""
    responses.add(responses.GET, f"{BASE_IG}/access_token",
                  json={"error_type": "OAuthException",
                        "error_message": "Invalid client_secret"})
    assert cli.main(["ig-setup", "--token", "breve",
                     "--app-secret", "sbagliato"]) == cli.EXIT_ERROR
    err = capsys.readouterr().err
    assert "Scambio del token" in err and "Invalid client_secret" in err


def test_ig_setup_instagram_senza_segreto_dice_dove_trovarlo(cfg, capsys, monkeypatch):
    monkeypatch.delenv("IG_APP_SECRET", raising=False)
    assert cli.main(["ig-setup", "--token", "breve"]) == cli.EXIT_ERROR
    assert "Chiave segreta di Instagram" in capsys.readouterr().err


@responses.activate
def test_ig_refresh_allunga_il_token(cfg, capsys):
    responses.add(responses.GET, f"{BASE_IG}/refresh_access_token",
                  json={"access_token": "IGQnuovo", "expires_in": 5184000})
    cfg.data["instagram"]["access_token"] = "IGQvecchio"
    assert cli.main(["ig-refresh"]) == cli.EXIT_OK
    assert "IG_ACCESS_TOKEN=IGQnuovo" in capsys.readouterr().out


def test_ig_refresh_non_esiste_sul_percorso_facebook(cfg, capsys):
    """Meglio dire come si fa che fallire con un 400 di Meta."""
    cfg.data["instagram"]["api_host"] = "graph.facebook.com"
    assert cli.main(["ig-refresh", "--token", "x"]) == cli.EXIT_ERROR
    assert "Graph API Explorer" in capsys.readouterr().err


@responses.activate
def test_token_status_instagram_valido(cfg, capsys):
    responses.add(responses.GET, f"{BASE_IG}/v21.0/me",
                  json={"id": "1", "username": "modenamagic"})
    cfg.data["instagram"]["access_token"] = "IGQ"
    assert cli.main(["token-status"]) == cli.EXIT_OK
    assert "ok: @modenamagic" in capsys.readouterr().out


@responses.activate
def test_token_status_instagram_scaduto(cfg, capsys):
    responses.add(responses.GET, f"{BASE_IG}/v21.0/me",
                  json={"error_message": "Session has expired"})
    cfg.data["instagram"]["access_token"] = "IGQ"
    assert cli.main(["token-status"]) == cli.EXIT_OK      # non e' un guasto
    assert "invalid" in capsys.readouterr().out


@responses.activate
def test_token_status_facebook_conta_i_giorni(cfg, capsys):
    import time

    cfg.data["instagram"]["api_host"] = "graph.facebook.com"
    cfg.data["instagram"]["access_token"] = "EAA"
    responses.add(responses.GET, f"{BASE_FB}/debug_token", json={"data": {
        "is_valid": True, "expires_at": int(time.time()) + 5 * 86400}})
    assert cli.main(["token-status"]) == cli.EXIT_OK
    assert "expiring: scade fra 4 giorni" in capsys.readouterr().out
