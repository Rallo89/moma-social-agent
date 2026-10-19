"""Copertina Facebook: griglia, contratto API, attivazione e recupero."""

import datetime as dt
import json
from unittest.mock import Mock

import pytest
import requests
import responses

from moma_social import cli, pipelines, publish
from moma_social.errors import ConfigError, PublishError
from moma_social.facebook import FacebookClient
from moma_social.models import Event, PostDraft
from moma_social.render import build_html, render

BASE = "https://graph.facebook.com/v26.0"


@pytest.fixture
def fb(cfg, tmp_path):
    cfg.data["facebook"].update(page_id="123", access_token="SEGRETO", publish_enabled=True)
    path = tmp_path / "cover.png"
    path.write_bytes(b"PNG")
    return cfg, str(path)


def _pagina(photo="10"):
    return {"id": "123", "name": "Pagina tornei", "cover": {"id": photo}}


@pytest.mark.parametrize("day,count", [(dt.date(2026, 8, 1), 6),
                                       (dt.date(2028, 2, 1), 5)])
def test_griglia_completa_e_italiana(cfg, day, count):
    weeks = pipelines._griglia_mensile(cfg, day, [])
    assert len(weeks) == count
    assert all(len(w) == 7 for w in weeks)
    assert weeks[0][day.weekday()]["numero"] == 1
    numbers = [d["numero"] for w in weeks for d in w if d["numero"]]
    assert numbers == list(range(1, 30 if day.month == 2 else 32))


def test_griglia_eventi_ordinati_e_overflow(cfg):
    day = dt.date(2026, 8, 1)
    events = [Event(day, "Nome lungo", "Modern", f"{hour}:00")
              for hour in (22, 21, 20, 19, 18)]
    cell = pipelines._griglia_mensile(cfg, day, events)[0][5]
    assert [e["ora"] for e in cell["eventi"]] == ["18:00", "19:00", "20:00"]
    assert cell["altri"] == 2
    html = build_html(cfg, "facebook_cover.html.j2", {
        "width": 1640, "height": 720, "mese": "agosto 2026", "link": "esempio.it",
        "settimane": pipelines._griglia_mensile(cfg, day, events),
    })
    assert "+2 eventi" in html and "Lunedì" in html and "agosto 2026" in html


@pytest.mark.parametrize("day,expected", [(dt.date(2026, 12, 30), "2027-01-01"),
                                           (dt.date(2028, 1, 30), "2028-02-01")])
def test_mensile_usa_tutti_eventi_e_separa_copertina(cfg, monkeypatch, tmp_path, day, expected):
    start = dt.date.fromisoformat(expected)
    events = [Event(start + dt.timedelta(days=n), "Torneo", "Modern", "21:00")
              for n in range(8)]
    monkeypatch.setattr(pipelines, "fetch_events", lambda *a: events)
    calls = []

    def fake_render(cfg, template, context, out_name, **kwargs):
        calls.append((template, context, kwargs))
        return tmp_path / f"{out_name}.png"

    monkeypatch.setattr(pipelines, "render", fake_render)
    cfg.data["posts"]["monthly_calendar"].update(rows_per_slide=1, max_carousel_slides=2)
    draft = pipelines.monthly_calendar(cfg, day)
    assert len(draft.images) == 2
    assert draft.artifacts["facebook_cover"] not in draft.images
    _, context, kwargs = calls[-1]
    assert kwargs == {"size": (1640, 720), "scale": 1}
    assert sum(len(d["eventi"]) for w in context["settimane"] for d in w) == 8
    assert str(start.year) in context["mese"]
    assert draft.meta["month_start"] == expected


def test_anteprima_senza_rete(fb):
    cfg, path = fb
    assert publish.publish_facebook_cover(cfg, path, "2026-08-01", dry_run=True)[
        "status"] == "dry-run"


def test_prima_attivazione_e_kill_switch(fb):
    cfg, path = fb
    assert publish.publish_facebook_cover(cfg, path, "2026-08-01")["status"] == "error"
    cfg.data["facebook"]["publish_enabled"] = False
    assert publish.publish_facebook_cover(cfg, path, "2026-08-01")["status"] == "skipped"


@responses.activate
def test_token_errato_o_permessi_insufficienti(fb):
    cfg, _ = fb
    responses.get(f"{BASE}/me", json={"id": "999", "name": "Altra pagina"})
    with pytest.raises(ConfigError, match="non appartiene"):
        FacebookClient(cfg).page()
    responses.replace(responses.GET, f"{BASE}/me",
                      json={"error": {"code": 200, "message": "SEGRETO"}}, status=403)
    with pytest.raises(PublishError) as exc:
        FacebookClient(cfg).page()
    assert "SEGRETO" not in str(exc.value)
    cfg.data["facebook"]["access_token"] = ""
    with pytest.raises(ConfigError):
        FacebookClient(cfg)


@responses.activate
def test_contratto_api_primo_successo_dedupe_e_force(fb):
    cfg, path = fb
    responses.get(f"{BASE}/me", json=_pagina())
    responses.get(f"{BASE}/me", json=_pagina())
    responses.get(f"{BASE}/me", json=_pagina("55"))
    responses.post(f"{BASE}/123/photos", json={"id": "55"})
    responses.post(f"{BASE}/123", json={"success": True})
    first = publish.publish_facebook_cover(cfg, path, "2026-08-01", bootstrap=True)
    assert first["status"] == "published"
    upload = next(c.request for c in responses.calls if c.request.url.endswith("/photos"))
    assert b'false' in upload.body and b'PNG' in upload.body
    update = next(c.request for c in responses.calls if c.request.url.endswith("/123"))
    assert "cover=55" in update.body and "no_feed_story=true" in update.body
    assert update.headers["Authorization"] == "Bearer SEGRETO"
    assert "SEGRETO" not in update.url
    count = len(responses.calls)
    assert publish.publish_facebook_cover(cfg, path, "2026-08-01")["status"] == "skipped"
    assert len(responses.calls) == count
    assert publish.publish_facebook_cover(cfg, path, "2026-08-01", force=True)[
        "status"] == "published"
    assert len([c for c in responses.calls if c.request.url.endswith("/photos")]) == 2


@responses.activate
def test_recupero_foto_caricata_ma_verifica_non_riuscita(fb):
    cfg, path = fb
    responses.get(f"{BASE}/me", json=_pagina())
    responses.post(f"{BASE}/123/photos", json={"id": "55"})
    responses.post(f"{BASE}/123", json={"success": True})
    first = publish.publish_facebook_cover(cfg, path, "2026-08-01", bootstrap=True)
    assert first["status"] == "error"
    responses.replace(responses.GET, f"{BASE}/me", json=_pagina("55"))
    second = publish.publish_facebook_cover(cfg, path, "2026-08-01", bootstrap=True)
    assert second["status"] == "published"
    assert len([c for c in responses.calls if c.request.url.endswith("/photos")]) == 1
    assert len([c for c in responses.calls if c.request.url.endswith("/123")]) == 1


@pytest.mark.parametrize("failing", ["instagram", "facebook"])
def test_canali_indipendenti(fb, monkeypatch, failing):
    cfg, path = fb
    draft = PostDraft("monthly_calendar", [path], "caption",
                      {"month_start": "2026-08-01"}, {"facebook_cover": path})
    ig = Mock(return_value={"status": "published"})
    facebook = Mock(return_value={"status": "published"})
    if failing == "instagram":
        ig.side_effect = ConfigError("token assente")
    else:
        facebook.return_value = {"status": "error"}
    monkeypatch.setattr(publish, "_publish_instagram_draft", ig)
    monkeypatch.setattr(publish, "publish_facebook_cover", facebook)
    result = publish.publish_draft(cfg, draft)
    assert result["status"] == "error"
    assert result["channels"][failing]["status"] == "error"
    ig.assert_called_once()
    facebook.assert_called_once()


def test_cli_anteprima_espone_e_salva_artefatti(fb, monkeypatch, capsys):
    cfg, path = fb
    draft = PostDraft("monthly_calendar", [path], "caption",
                      {"month_start": "2026-08-01"}, {"facebook_cover": path})
    monkeypatch.setattr(cli.config, "load", lambda *a: cfg)
    monkeypatch.setattr(cli, "drafts", lambda *a, **kw: [draft])
    assert cli.main(["monthly", "--no-publish"]) == 0
    assert "Artefatto facebook_cover" in capsys.readouterr().out
    meta = cfg.resolve_path(cfg.get("render.output_dir")) / "cover.json"
    assert json.loads(meta.read_text(encoding="utf-8"))["artifacts"] == draft.artifacts
    assert not publish.ledger_path(cfg).exists()


@responses.activate
def test_fb_setup_sola_lettura(fb, monkeypatch, capsys):
    cfg, _ = fb
    monkeypatch.setattr(cli.config, "load", lambda *a: cfg)
    responses.get(f"{BASE}/me", json=_pagina())
    assert cli.main(["fb-setup"]) == 0
    assert "Pagina tornei" in capsys.readouterr().out
    assert all(c.request.method == "GET" for c in responses.calls)


def test_errore_rete_non_espone_token(fb, monkeypatch):
    cfg, _ = fb
    monkeypatch.setattr(requests, "request", Mock(side_effect=requests.RequestException("SEGRETO")))
    with pytest.raises(PublishError) as exc:
        FacebookClient(cfg).page()
    assert "SEGRETO" not in str(exc.value)


@responses.activate
@pytest.mark.parametrize("failing", ["instagram", "facebook"])
def test_rilancio_riprende_solo_canale_fallito(fb, failing):
    cfg, path = fb
    cfg.data["instagram"].update(ig_user_id="999", access_token="IG_TOKEN")
    cfg.data["media"]["backend"] = "imgbb"
    cfg.data["media"]["imgbb"]["api_key"] = "KEY"
    publish.record(cfg, {"kind": "facebook_cover", "page_id": "123",
                         "api_version": "v26.0", "status": "published"})
    draft = PostDraft("monthly_calendar", [path], "caption",
                      {"month_start": "2026-08-01"}, {"facebook_cover": path})
    ig_base = "https://graph.instagram.com/v21.0"
    responses.post("https://api.imgbb.com/1/upload", json={"data": {"url": "https://cdn/x.png"}})
    responses.post(f"{ig_base}/999/media", json={"id": "C"})
    responses.get(f"{ig_base}/C", json={"status_code": "FINISHED"})
    ig_publish = responses.post(f"{ig_base}/999/media_publish", json={"id": "IG_POST"})
    responses.get(f"{ig_base}/IG_POST", json={"permalink": "https://instagram.com/p/example"})
    responses.get(f"{BASE}/me", json=_pagina("55"))
    responses.post(f"{BASE}/123/photos", json={"id": "55"})
    if failing == "instagram":
        responses.replace(responses.POST, f"{ig_base}/999/media_publish",
                          json={"error": {"message": "errore", "code": 200}}, status=403)
    else:
        responses.replace(responses.GET, f"{BASE}/me",
                          json={"error": {"code": 200}}, status=403)
    first = publish.publish_draft(cfg, draft)
    assert first["status"] == "error"
    succeeded = "facebook" if failing == "instagram" else "instagram"
    assert first["channels"][succeeded]["status"] == "published"
    first_calls = len(responses.calls)
    if failing == "instagram":
        responses.replace(responses.POST, f"{ig_base}/999/media_publish", json={"id": "IG_POST"})
    else:
        responses.replace(responses.GET, f"{BASE}/me", json=_pagina("55"))
    second = publish.publish_draft(cfg, draft)
    assert second["status"] == "published"
    assert second["channels"][succeeded]["status"] == "skipped"
    new_calls = responses.calls[first_calls:]
    assert all(("graph.instagram.com" in c.request.url or "imgbb.com" in c.request.url)
               if failing == "instagram" else "graph.facebook.com" in c.request.url
               for c in new_calls)
    if failing == "facebook":
        assert ig_publish.call_count == 1


def test_cli_esito_parziale_fallisce_e_riassume_canali(fb, monkeypatch, tmp_path):
    cfg, path = fb
    monkeypatch.setattr(cli.config, "load", lambda *a: cfg)
    monkeypatch.setattr(cli, "drafts", lambda *a, **kw: [PostDraft(
        "monthly_calendar", [path], "caption", {"month_start": "2026-08-01"})])
    monkeypatch.setattr(cli, "publish_draft", lambda *a, **kw: {
        "status": "error", "channels": {"instagram": {"status": "published"},
                                          "facebook": {"status": "error", "error": "permessi"}}})
    summary = tmp_path / "summary.md"
    monkeypatch.setenv("GITHUB_STEP_SUMMARY", str(summary))
    assert cli.main(["monthly"]) == 1
    text = summary.read_text(encoding="utf-8")
    assert "instagram" in text and "facebook" in text and "permessi" in text


@responses.activate
def test_pagina_senza_copertina(fb):
    cfg, _ = fb
    responses.get(f"{BASE}/me", json={"id": "123", "name": "Pagina", "cover": None})
    assert FacebookClient(cfg).verify_cover("55") is False


def test_mcp_mensile_espone_copertina_e_dry_run(cfg, monkeypatch, tmp_path):
    pytest.importorskip("mcp")
    from moma_social import mcp_server
    monkeypatch.setattr(mcp_server, "_cfg", lambda: cfg)

    def fake_render(cfg, template, context, out_name, **kwargs):
        path = tmp_path / f"{out_name}.png"
        path.write_bytes(b"PNG")
        return path

    monkeypatch.setattr(pipelines, "render", fake_render)
    preview = json.loads(mcp_server.genera_post("monthly_calendar", "2026-02-28"))[0]
    assert preview["artifacts"]["facebook_cover"] not in preview["immagini"]
    assert preview["carosello"] is True
    result = json.loads(mcp_server.pubblica_post("monthly_calendar", "2026-02-28"))[0]
    assert result["status"] == "dry-run"
    assert all(e["status"] == "dry-run" for e in result["channels"].values())


@pytest.mark.slow
def test_png_copertina_dimensioni(cfg):
    from PIL import Image
    path = render(cfg, "facebook_cover.html.j2", {
        "mese": "agosto 2026", "link": "esempio.it",
        "settimane": pipelines._griglia_mensile(cfg, dt.date(2026, 8, 1), []),
    }, "facebook-cover", size=(1640, 720), scale=1)
    with Image.open(path) as img:
        assert img.size == (1640, 720)


@pytest.mark.parametrize("channel", ["instagram", "facebook", "both"])
@pytest.mark.parametrize("flags", [{}, {"dry_run": True}, {"force": True}])
def test_scelta_canale_isola_pubblicazione_e_flag(fb, monkeypatch, channel, flags):
    cfg, path = fb
    draft = PostDraft("monthly_calendar", [path], "caption",
                      {"month_start": "2026-08-01"}, {"facebook_cover": path})
    ig = Mock(return_value={"status": "published"})
    facebook = Mock(return_value={"status": "published"})
    monkeypatch.setattr(publish, "_publish_instagram_draft", ig)
    monkeypatch.setattr(publish, "publish_facebook_cover", facebook)
    result = publish.publish_draft(cfg, draft, channel=channel, **flags)
    assert result["status"] == "published"
    expected_flags = {"dry_run": flags.get("dry_run", False), "force": flags.get("force", False)}
    if channel in ("instagram", "both"):
        ig.assert_called_once_with(cfg, draft, **expected_flags)
    else:
        ig.assert_not_called()
    if channel in ("facebook", "both"):
        if channel == "facebook":
            expected_flags["bootstrap"] = True
        facebook.assert_called_once_with(cfg, path, "2026-08-01", **expected_flags)
    else:
        facebook.assert_not_called()


@responses.activate
@pytest.mark.parametrize("channel,kinds", [
    ("instagram", {"monthly_calendar"}), ("facebook", {"facebook_cover"}),
    ("both", {"monthly_calendar", "facebook_cover"}),
])
def test_dry_run_registra_solo_canali_scelti_senza_rete(fb, channel, kinds):
    cfg, path = fb
    draft = PostDraft("monthly_calendar", [path], "caption",
                      {"month_start": "2026-08-01"}, {"facebook_cover": path})
    result = publish.publish_draft(cfg, draft, channel=channel, dry_run=True)
    assert result["status"] == "dry-run"
    entries = [json.loads(line) for line in publish.ledger_path(cfg).read_text().splitlines()]
    assert {entry["kind"] for entry in entries} == kinds
    assert all(entry["status"] == "dry-run" for entry in entries)
    assert not responses.calls


@pytest.mark.parametrize("args,channel", [([], "both"), (["--channel", "instagram"], "instagram"),
                                        (["--channel", "facebook"], "facebook")])
def test_cli_inoltra_scelta_canale(fb, monkeypatch, args, channel):
    cfg, path = fb
    draft = PostDraft("monthly_calendar", [path], "caption",
                      {"month_start": "2026-08-01"}, {"facebook_cover": path})
    monkeypatch.setattr(cli.config, "load", lambda *a: cfg)
    monkeypatch.setattr(cli, "drafts", lambda *a, **kw: [draft])
    publisher = Mock(return_value={"status": "dry-run"})
    monkeypatch.setattr(cli, "publish_draft", publisher)
    assert cli.main(["monthly", "--dry-run", "--force", *args]) == 0
    publisher.assert_called_once_with(cfg, draft, channel=channel, dry_run=True, force=True)


def test_facebook_senza_copertina_non_ripiega_su_instagram(fb, monkeypatch):
    cfg, path = fb
    ig = Mock()
    monkeypatch.setattr(publish, "_publish_instagram_draft", ig)
    draft = PostDraft("monthly_calendar", [path], "caption")
    with pytest.raises(ConfigError, match="copertina generata"):
        publish.publish_draft(cfg, draft, channel="facebook")
    ig.assert_not_called()


@responses.activate
def test_prima_impostazione_dal_mensile_facebook(fb):
    cfg, path = fb
    draft = PostDraft("monthly_calendar", [path], "caption",
                      {"month_start": "2026-08-01"}, {"facebook_cover": path})
    responses.get(f"{BASE}/me", json=_pagina("55"))
    responses.post(f"{BASE}/123/photos", json={"id": "55"})
    result = publish.publish_draft(cfg, draft, channel="facebook")
    assert result["status"] == "published"
    assert set(result["channels"]) == {"facebook"}
    assert all("graph.facebook.com" in c.request.url for c in responses.calls)
    # Dopo la prima verifica il percorso automatico e' attivo, senza nuovo upload.
    assert publish.publish_facebook_cover(cfg, path, "2026-08-01")["status"] == "skipped"


@responses.activate
def test_scelta_facebook_rispetta_kill_switch(fb):
    cfg, path = fb
    cfg.data["facebook"]["publish_enabled"] = False
    draft = PostDraft("monthly_calendar", [path], "caption",
                      {"month_start": "2026-08-01"}, {"facebook_cover": path})
    result = publish.publish_draft(cfg, draft, channel="facebook")
    assert result["channels"]["facebook"]["status"] == "skipped"
    assert not responses.calls
