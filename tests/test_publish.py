"""Pubblicazione: dedupe, kill switch, dry-run, errori Graph API."""

import json

import pytest
import responses

from moma_social.errors import ConfigError, PublishError
from moma_social.instagram import InstagramClient
from moma_social.models import PostDraft
from moma_social.publish import dedupe_key, ledger_path, publish_draft
from moma_social.uploader import upload

# L'host e' quello configurato: le stesse chiamate valgono per entrambi i
# percorsi di autenticazione, e i test devono seguire la config, non fissarne uno.
API = "https://graph.instagram.com/v21.0"


@pytest.fixture
def draft(tmp_path):
    image = tmp_path / "out" / "slide.png"
    image.parent.mkdir(parents=True, exist_ok=True)
    image.write_bytes(b"\x89PNG finto")
    return PostDraft(kind="leg_results", images=[str(image)], caption="ciao",
                     meta={"day": "2026-03-11", "format": "Modern"})


def _credentials(cfg):
    cfg.data["instagram"]["ig_user_id"] = "999"
    cfg.data["instagram"]["access_token"] = "TOKEN"
    cfg.data["media"]["backend"] = "imgbb"
    cfg.data["media"]["imgbb"]["api_key"] = "K"


def test_dedupe_key_stabile(draft):
    assert dedupe_key(draft) == "leg_results:2026-03-11:Modern"


def test_il_calendario_mensile_ha_una_chiave_per_mese():
    """Senza `month_start` la chiave sarebbe costante: pubblicato ottobre,
    novembre risulterebbe gia' uscito e non uscirebbe mai."""
    from moma_social.pipelines import PostDraft
    def mensile(mese):
        return PostDraft(kind="monthly_calendar", images=[], caption="",
                         meta={"month_start": mese})
    assert dedupe_key(mensile("2026-10-01")) != dedupe_key(mensile("2026-11-01"))
    assert "2026-10-01" in dedupe_key(mensile("2026-10-01"))


def test_dry_run_non_chiama_la_rete(cfg, draft):
    entry = publish_draft(cfg, draft, dry_run=True)
    assert entry["status"] == "dry-run"
    assert ledger_path(cfg).exists()


def test_dry_run_salva_caption_e_metadati(cfg, draft):
    publish_draft(cfg, draft, dry_run=True)
    out = ledger_path(cfg).parent / "out"
    assert (out / "slide.caption.txt").read_text(encoding="utf-8") == "ciao"
    assert json.loads((out / "slide.json").read_text(encoding="utf-8"))["kind"] == "leg_results"


def test_kill_switch_blocca_la_pubblicazione(cfg, draft):
    cfg.data["instagram"]["publish_enabled"] = False
    entry = publish_draft(cfg, draft)
    assert entry["status"] == "skipped"
    assert "publish_enabled" in entry["reason"]


@responses.activate
def test_pubblicazione_immagine_singola(cfg, draft):
    _credentials(cfg)
    responses.post("https://api.imgbb.com/1/upload",
                   json={"data": {"url": "https://cdn/x.png"}})
    responses.post(f"{API}/999/media", json={"id": "CONTAINER"})
    responses.get(f"{API}/CONTAINER", json={"status_code": "FINISHED"})
    responses.post(f"{API}/999/media_publish", json={"id": "POST1"})
    responses.get(f"{API}/POST1", json={"permalink": "https://instagram.com/p/abc"})

    entry = publish_draft(cfg, draft)
    assert entry["status"] == "published"
    assert entry["post_id"] == "POST1"
    assert entry["permalink"] == "https://instagram.com/p/abc"


@responses.activate
def test_secondo_run_non_ripubblica(cfg, draft):
    _credentials(cfg)
    responses.post("https://api.imgbb.com/1/upload",
                   json={"data": {"url": "https://cdn/x.png"}})
    responses.post(f"{API}/999/media", json={"id": "C"})
    responses.get(f"{API}/C", json={"status_code": "FINISHED"})
    responses.post(f"{API}/999/media_publish", json={"id": "POST1"})
    responses.get(f"{API}/POST1", json={"permalink": "p"})

    assert publish_draft(cfg, draft)["status"] == "published"
    second = publish_draft(cfg, draft)
    assert second["status"] == "skipped"
    assert second["post_id"] == "POST1"


@responses.activate
def test_force_ripubblica(cfg, draft):
    _credentials(cfg)
    responses.post("https://api.imgbb.com/1/upload",
                   json={"data": {"url": "https://cdn/x.png"}})
    responses.post(f"{API}/999/media", json={"id": "C"})
    responses.get(f"{API}/C", json={"status_code": "FINISHED"})
    responses.post(f"{API}/999/media_publish", json={"id": "POST2"})
    responses.get(f"{API}/POST2", json={"permalink": "p"})

    publish_draft(cfg, draft)
    assert publish_draft(cfg, draft, force=True)["status"] == "published"


@responses.activate
def test_errore_graph_api_registrato(cfg, draft):
    _credentials(cfg)
    responses.post("https://api.imgbb.com/1/upload",
                   json={"data": {"url": "https://cdn/x.png"}})
    responses.post(f"{API}/999/media",
                   json={"error": {"code": 190, "message": "Token scaduto"}})

    with pytest.raises(PublishError, match="190"):
        publish_draft(cfg, draft)
    last = json.loads(ledger_path(cfg).read_text(encoding="utf-8").splitlines()[-1])
    assert last["status"] == "error"


@responses.activate
def test_carosello_crea_i_figli_in_ordine(cfg, tmp_path):
    _credentials(cfg)
    images = []
    for name in ("risultati.png", "classifica.png"):
        path = tmp_path / "out" / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"png")
        images.append(str(path))

    responses.post("https://api.imgbb.com/1/upload",
                   json={"data": {"url": "https://cdn/x.png"}})
    responses.post(f"{API}/999/media", json={"id": "C1"})
    responses.get(f"{API}/C1", json={"status_code": "FINISHED"})
    responses.post(f"{API}/999/media_publish", json={"id": "POST"})
    responses.get(f"{API}/POST", json={"permalink": "p"})

    client = InstagramClient(cfg)
    assert client.publish_post(["https://a/1.png", "https://a/2.png"], "c") == "POST"
    carousel = [call.request for call in responses.calls
                if call.request.url.endswith("/999/media")][-1]
    assert "media_type=CAROUSEL" in carousel.body
    assert "children=C1%2CC1" in carousel.body


@responses.activate
def test_container_in_errore(cfg):
    _credentials(cfg)
    responses.post(f"{API}/999/media", json={"id": "C"})
    responses.get(f"{API}/C", json={"status_code": "ERROR", "status": "immagine non valida"})
    with pytest.raises(PublishError, match="ERROR"):
        InstagramClient(cfg).publish_post(["https://a/1.png"], "c")


def test_credenziali_mancanti(cfg):
    cfg.data["instagram"]["ig_user_id"] = ""
    cfg.data["instagram"]["access_token"] = ""
    with pytest.raises(ConfigError, match="IG_USER_ID"):
        InstagramClient(cfg).check()


def test_backend_media_assente(cfg, tmp_path):
    cfg.data["media"]["backend"] = "none"
    with pytest.raises(ConfigError, match="dry-run"):
        upload(cfg, tmp_path)


@responses.activate
def test_carosello_oltre_il_limite_viene_rifiutato(cfg):
    """Meglio un errore chiaro prima di caricare 13 immagini per niente."""
    from moma_social.instagram import MAX_CAROUSEL

    _credentials(cfg)
    urls = [f"https://a/{i}.png" for i in range(MAX_CAROUSEL + 1)]
    with pytest.raises(PublishError, match=str(MAX_CAROUSEL)):
        InstagramClient(cfg).publish_post(urls, "caption")
    assert not responses.calls          # nessuna chiamata sprecata


def test_imgbb_rifiuta_una_scadenza_troppo_corta(cfg):
    """Sotto il minuto imgbb dice solo "invalid parameter"."""
    from pathlib import Path

    cfg.data["media"]["backend"] = "imgbb"
    cfg.data["media"]["imgbb"]["api_key"] = "finta"
    cfg.data["media"]["imgbb"]["expiration"] = 30
    with pytest.raises(ConfigError, match="60 secondi"):
        upload(cfg, Path("data/samples/events.json"))


@responses.activate
def test_lo_stesso_client_parla_con_entrambi_gli_host(cfg):
    """Instagram Login e Facebook Login: cambia l'host, non le chiamate."""
    cfg.data["instagram"]["ig_user_id"] = "999"
    cfg.data["instagram"]["access_token"] = "TOKEN"
    cfg.data["instagram"]["api_host"] = "graph.facebook.com"
    client = InstagramClient(cfg)
    assert client.base == "https://graph.facebook.com/v21.0"
    assert not client.instagram_login

    responses.add(responses.GET, f"{client.base}/{client.ig_user_id}",
                  json={"id": "1", "username": "modenamagic"})
    def campi(chiamata):
        from urllib.parse import parse_qs, urlparse
        return parse_qs(urlparse(chiamata.request.url).query)["fields"][0].split(",")

    client.check()
    # Su Facebook si puo' chiedere `name`; su Instagram quel campo non esiste
    # e chiederlo farebbe fallire l'intera chiamata.
    assert "name" in campi(responses.calls[0])

    cfg.data["instagram"]["api_host"] = "graph.instagram.com"
    altro = InstagramClient(cfg)
    assert altro.instagram_login
    responses.add(responses.GET, f"{altro.base}/{altro.ig_user_id}",
                  json={"id": "1", "username": "modenamagic"})
    altro.check()
    assert "name" not in campi(responses.calls[1])
    assert "username" in campi(responses.calls[1])


@responses.activate
def test_i_coautori_vanno_solo_sul_contenitore_con_la_caption(cfg):
    """Le singole slide non hanno coautori: il post e' uno."""
    from urllib.parse import parse_qs

    cfg.data["instagram"]["ig_user_id"] = "999"
    cfg.data["instagram"]["access_token"] = "TOKEN"
    cfg.data["instagram"]["collaborators"] = ["unocritico"]
    client = InstagramClient(cfg)

    responses.add(responses.POST, f"{client.base}/999/media", json={"id": "c1"})
    responses.add(responses.GET, f"{client.base}/c1",
                  json={"status_code": "FINISHED"})
    responses.add(responses.POST, f"{client.base}/999/media", json={"id": "c2"})
    responses.add(responses.GET, f"{client.base}/c2",
                  json={"status_code": "FINISHED"})
    responses.add(responses.POST, f"{client.base}/999/media", json={"id": "pad"})
    responses.add(responses.GET, f"{client.base}/pad",
                  json={"status_code": "FINISHED"})
    responses.add(responses.POST, f"{client.base}/999/media_publish",
                  json={"id": "post"})

    client.publish_post(["https://a/1.png", "https://a/2.png"], "caption")
    corpi = [parse_qs(c.request.body) for c in responses.calls
             if c.request.method == "POST" and c.request.url.endswith("/media")]
    figli = [b for b in corpi if "is_carousel_item" in b]
    padre = [b for b in corpi if "media_type" in b]
    assert all("collaborators" not in b for b in figli)
    assert padre and padre[0]["collaborators"] == ['["unocritico"]']


@responses.activate
def test_un_rifiuto_dei_coautori_dice_dove_guardare(cfg):
    """Senza questo, l'errore di Meta manda a cercare nell'immagine."""
    cfg.data["instagram"]["ig_user_id"] = "999"
    cfg.data["instagram"]["access_token"] = "TOKEN"
    cfg.data["instagram"]["collaborators"] = ["unocritico"]
    client = InstagramClient(cfg)
    responses.add(responses.POST, f"{client.base}/999/media", json={
        "error": {"code": 100, "message": "Invalid parameter: collaborators"}})
    with pytest.raises(PublishError, match="instagram.collaborators"):
        client.publish_post(["https://a/1.png"], "caption")


def test_la_chiocciola_nel_coautore_non_arriva_a_meta(cfg):
    """Si copia l'username dal profilo e viene con la "@" davanti."""
    cfg.data["instagram"]["collaborators"] = ["@uno.critico", "  ", "moma "]
    assert InstagramClient(cfg).collaborators == ["uno.critico", "moma"]
