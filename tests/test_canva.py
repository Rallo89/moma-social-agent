"""Collegamento Canva: token, rotazione, export, sync.

Tutto il dialogo con Canva e' simulato: il flusso e' verificabile senza
credenziali vere, ed e' l'unico modo di coprire la rotazione del refresh
token, che e' il punto in cui questa integrazione si rompe davvero.
"""

import json
import time

import pytest
import responses

from moma_social.canva import (
    API_BASE,
    TOKEN_URL,
    AssetSpec,
    CanvaClient,
    CanvaError,
    _pkce_pair,
    assets_from_config,
    sync,
)
from moma_social.errors import ConfigError

PNG_A = b"\x89PNG-primo-sfondo"
PNG_B = b"\x89PNG-secondo-sfondo"


@pytest.fixture(autouse=True)
def polling_immediato(monkeypatch):
    """Niente attese vere fra un poll e l'altro del job di export."""
    monkeypatch.setattr("moma_social.canva.POLL_INTERVAL", 0)


@pytest.fixture
def canva_cfg(cfg, tmp_path):
    cfg.data["canva"] = {
        "client_id": "CID",
        "client_secret": "CSECRET",
        "redirect_port": 8721,
        "token_file": str(tmp_path / "canva-tokens.json"),
        "export_quality": "regular",
        "assets": [
            {"design_id": "DAF111", "target": str(tmp_path / "sfondo_calendario.png")},
        ],
    }
    return cfg


@pytest.fixture
def con_token(canva_cfg):
    """Token gia' presenti e validi."""
    client = CanvaClient(canva_cfg)
    client.token_file.write_text(json.dumps({
        "access_token": "AT-vecchio",
        "refresh_token": "RT-vecchio",
        "expires_at": int(time.time()) + 3600,
    }), encoding="utf-8")
    return canva_cfg


# ── PKCE ────────────────────────────────────────────────────────────────────
def test_pkce_challenge_deriva_dal_verifier():
    import base64
    import hashlib

    verifier, challenge = _pkce_pair()
    atteso = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).decode().rstrip("=")
    assert challenge == atteso
    assert "=" not in verifier and "=" not in challenge


def test_pkce_e_diverso_a_ogni_chiamata():
    assert _pkce_pair()[0] != _pkce_pair()[0]


# ── configurazione ──────────────────────────────────────────────────────────
def test_assets_dalla_config(canva_cfg):
    specs = assets_from_config(canva_cfg)
    assert len(specs) == 1
    assert specs[0].design_id == "DAF111"
    assert specs[0].page == 1


def test_asset_senza_target(canva_cfg):
    canva_cfg.data["canva"]["assets"] = [{"design_id": "DAF111"}]
    with pytest.raises(ConfigError, match="target"):
        assets_from_config(canva_cfg)


def test_nessun_asset_configurato(canva_cfg):
    canva_cfg.data["canva"]["assets"] = []
    with pytest.raises(ConfigError, match="canva.assets"):
        assets_from_config(canva_cfg)


def test_nome_asset_dal_file():
    assert AssetSpec("D", "a/b/sfondo.png").name == "sfondo.png"


# ── token ───────────────────────────────────────────────────────────────────
def test_credenziali_mancanti(canva_cfg):
    canva_cfg.data["canva"]["client_id"] = ""
    with pytest.raises(ConfigError, match="CANVA_CLIENT_ID"):
        CanvaClient(canva_cfg)._require_client()


def test_senza_token_dice_di_autorizzare(canva_cfg):
    with pytest.raises(ConfigError, match="canva-auth"):
        CanvaClient(canva_cfg).load_tokens()


@responses.activate
def test_scambio_codice_salva_i_token(canva_cfg):
    responses.post(TOKEN_URL, json={
        "access_token": "AT-1", "refresh_token": "RT-1", "expires_in": 14400,
    })
    client = CanvaClient(canva_cfg)
    client.exchange_code("CODE", "VERIFIER", "http://127.0.0.1:8721")

    salvati = client.load_tokens()
    assert salvati["access_token"] == "AT-1"
    assert salvati["refresh_token"] == "RT-1"
    assert salvati["expires_at"] > time.time()


@responses.activate
def test_richiesta_token_usa_basic_auth(canva_cfg):
    responses.post(TOKEN_URL, json={"access_token": "AT", "expires_in": 100})
    CanvaClient(canva_cfg).exchange_code("C", "V", "R")
    import base64
    atteso = "Basic " + base64.b64encode(b"CID:CSECRET").decode()
    assert responses.calls[0].request.headers["Authorization"] == atteso


@responses.activate
def test_refresh_ruota_e_salva_il_nuovo_token(con_token):
    """Il refresh token e' monouso: quello nuovo deve finire su disco subito."""
    responses.post(TOKEN_URL, json={
        "access_token": "AT-nuovo", "refresh_token": "RT-nuovo", "expires_in": 14400,
    })
    client = CanvaClient(con_token)
    assert client.refresh() == "AT-nuovo"
    assert client.load_tokens()["refresh_token"] == "RT-nuovo"


@responses.activate
def test_token_valido_non_viene_rinnovato(con_token):
    assert CanvaClient(con_token).access_token() == "AT-vecchio"
    assert len(responses.calls) == 0


@responses.activate
def test_token_scaduto_viene_rinnovato(canva_cfg):
    client = CanvaClient(canva_cfg)
    client.token_file.write_text(json.dumps({
        "access_token": "AT-scaduto", "refresh_token": "RT",
        "expires_at": int(time.time()) - 10,
    }), encoding="utf-8")
    responses.post(TOKEN_URL, json={
        "access_token": "AT-fresco", "refresh_token": "RT2", "expires_in": 14400,
    })
    assert client.access_token() == "AT-fresco"


@responses.activate
def test_catena_di_refresh_rotta(con_token):
    """E' il guasto tipico: messaggio comprensibile, non uno stack trace."""
    responses.post(TOKEN_URL, json={
        "error": "invalid_grant",
        "error_description": "Refresh token used twice.",
    })
    with pytest.raises(CanvaError, match="invalid_grant"):
        CanvaClient(con_token).refresh()


# ── export ──────────────────────────────────────────────────────────────────
@responses.activate
def test_export_attende_il_job(con_token):
    responses.post(f"{API_BASE}/exports",
                   json={"job": {"id": "J1", "status": "in_progress"}})
    responses.get(f"{API_BASE}/exports/J1",
                  json={"job": {"id": "J1", "status": "in_progress"}})
    responses.get(f"{API_BASE}/exports/J1",
                  json={"job": {"id": "J1", "status": "success",
                                "urls": ["https://cdn.canva/a.png"]}})
    urls = CanvaClient(con_token).export_png("DAF111")
    assert urls == ["https://cdn.canva/a.png"]


@responses.activate
def test_export_fallito(con_token):
    responses.post(f"{API_BASE}/exports", json={"job": {"id": "J1", "status": "failed",
                   "error": {"code": "design_not_found", "message": "nope"}}})
    responses.get(f"{API_BASE}/exports/J1", json={"job": {"id": "J1", "status": "failed",
                  "error": {"code": "design_not_found", "message": "nope"}}})
    with pytest.raises(CanvaError, match="design_not_found"):
        CanvaClient(con_token).export_png("DAF111")


@responses.activate
def test_design_inesistente(con_token):
    responses.post(f"{API_BASE}/exports", json={"message": "not found"}, status=404)
    with pytest.raises(CanvaError, match="design_id"):
        CanvaClient(con_token).export_png("SBAGLIATO")


# ── sync ────────────────────────────────────────────────────────────────────
def _mock_export(design_id="DAF111", urls=("https://cdn.canva/a.png",)):
    responses.post(f"{API_BASE}/exports",
                   json={"job": {"id": "J", "status": "success", "urls": list(urls)}})
    responses.get(f"{API_BASE}/exports/J",
                  json={"job": {"id": "J", "status": "success", "urls": list(urls)}})


@responses.activate
def test_sync_scrive_lo_sfondo(con_token):
    _mock_export()
    responses.get("https://cdn.canva/a.png", body=PNG_A)
    report = sync(con_token)
    assert report[0]["stato"] == "aggiornato"
    assert (con_token.resolve_path(report[0]["file"])).read_bytes() == PNG_A


@responses.activate
def test_sync_riconosce_lo_sfondo_invariato(con_token):
    target = con_token.resolve_path(con_token.data["canva"]["assets"][0]["target"])
    target.write_bytes(PNG_A)
    _mock_export()
    responses.get("https://cdn.canva/a.png", body=PNG_A)
    assert sync(con_token)[0]["stato"] == "invariato"


@responses.activate
def test_check_non_scrive_nulla(con_token):
    _mock_export()
    responses.get("https://cdn.canva/a.png", body=PNG_A)
    report = sync(con_token, check=True)
    assert report[0]["stato"] == "da aggiornare"
    assert not con_token.resolve_path(report[0]["file"]).exists()


@responses.activate
def test_sync_sceglie_la_pagina_giusta(con_token, tmp_path):
    """Un solo design con piu' pagine: ogni pagina e' uno sfondo diverso."""
    con_token.data["canva"]["assets"] = [
        {"design_id": "DAF111", "page": 2, "target": str(tmp_path / "sfondo2.png")},
    ]
    _mock_export(urls=("https://cdn.canva/p1.png", "https://cdn.canva/p2.png"))
    responses.get("https://cdn.canva/p1.png", body=PNG_A)
    responses.get("https://cdn.canva/p2.png", body=PNG_B)
    report = sync(con_token)
    assert con_token.resolve_path(report[0]["file"]).read_bytes() == PNG_B


@responses.activate
def test_pagina_inesistente(con_token, tmp_path):
    con_token.data["canva"]["assets"] = [
        {"design_id": "DAF111", "page": 5, "target": str(tmp_path / "x.png")},
    ]
    _mock_export()
    with pytest.raises(CanvaError, match="pagina 5"):
        sync(con_token)


@responses.activate
def test_only_filtra_un_solo_sfondo(con_token, tmp_path):
    con_token.data["canva"]["assets"].append(
        {"design_id": "DAF222", "target": str(tmp_path / "sfondo_formato.png")}
    )
    _mock_export()
    responses.get("https://cdn.canva/a.png", body=PNG_A)
    report = sync(con_token, only="sfondo_formato.png")
    assert len(report) == 1
    assert report[0]["design_id"] == "DAF222"


def test_only_senza_corrispondenze(con_token):
    with pytest.raises(ConfigError, match="inesistente"):
        sync(con_token, only="inesistente")
