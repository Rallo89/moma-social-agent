"""Storie: selezione per data o ID e pubblicazione senza feed."""

import datetime as dt
from pathlib import Path

import pytest
import responses
from PIL import Image

from moma_social import pipelines
from moma_social.cli import build_parser, cmd_post
from moma_social.errors import ConfigError, SourceError
from moma_social.instagram import InstagramClient
from moma_social.models import Event, PostDraft
from moma_social.publish import dedupe_key, publish_draft
from moma_social.render import build_html, render
from moma_social.repos import fetch_event_by_id
from moma_social.storyutil import story_jpeg


def _event(day, ident, title="Modern Fall"):
    return Event(
        date=day, tournament_id=ident, title=title, format="Modern",
        venue="Uno Critico",
    )


def test_due_storie_per_due_giorni_e_tornei_distinti(cfg, monkeypatch, tmp_path):
    today = dt.date(2026, 10, 7)
    first = "92d6beb5-a1e3-44ad-9a65-7c8e982d7e44"
    second = "161dd0a4-997a-493d-a2b6-5d85186687f8"
    events = [_event(today, first), _event(today, second, "Modern Extra"),
              _event(today + dt.timedelta(days=1), first)]
    events[0].entry_fee = "15"
    monkeypatch.setattr(pipelines, "fetch_events", lambda *_: events)
    contexts = []

    def fake_render(cfg, template, context, name, size, scale):
        contexts.append((template, context, size))
        assert scale == 1
        path = tmp_path / f"{name}.png"
        Image.new("RGB", (2160, 3840), "#14171a").save(path)
        return path

    monkeypatch.setattr(pipelines, "render", fake_render)
    drafts = pipelines.story_events_batch(cfg, today)
    assert len(drafts) == 3
    assert [d.meta["phase"] for d in drafts] == ["oggi", "oggi", "domani"]
    assert len({dedupe_key(d) for d in drafts}) == 3
    assert all(Path(d.images[0]).suffix == ".jpg" for d in drafts)
    assert all(Image.open(d.images[0]).size == (1080, 1920) for d in drafts)
    assert all(t == "storia_evento.html.j2" and size == (1080, 1920)
               for t, _, size in contexts)
    assert all("qr" not in context for _, context, _ in contexts)
    assert contexts[0][1]["quota"] == "15 €"
    assert contexts[1][1]["quota"] == "10 €"
    assert contexts[0][1]["illustrazione"]["artist"] == "Simon Dominic"


def test_id_mancante_salta_solo_quel_torneo(cfg, monkeypatch, tmp_path):
    day = dt.date(2026, 10, 7)
    invalid = _event(day, "")
    valid = _event(day, "161dd0a4-997a-493d-a2b6-5d85186687f8")
    monkeypatch.setattr(pipelines, "fetch_events", lambda *_: [invalid, valid])
    monkeypatch.setattr(pipelines, "render", lambda *args, **kwargs: tmp_path / "story.png")
    monkeypatch.setattr(pipelines, "story_jpeg", lambda path, *_: path.with_suffix(".jpg"))
    with pytest.warns(UserWarning, match="Storia saltata"):
        drafts = pipelines.story_events_batch(cfg, day)
    assert len(drafts) == 1
    assert drafts[0].meta["tournament_id"] == valid.tournament_id


def test_ricerca_torneo_per_uuid_completo(cfg, monkeypatch):
    ident = "92d6beb5-a1e3-44ad-9a65-7c8e982d7e44"
    cfg.data["sources"]["events"] = {
        "url": "https://example.test/events?from={date_from}",
        "by_id_url": "https://example.test/events?id=eq.{tournament_id}",
        "kind": "json",
        "map": {"date": "data", "tournament_id": "torneo_id", "title": "titolo"},
    }
    with responses.RequestsMock() as mock:
        mock.add(responses.GET, f"https://example.test/events?id=eq.{ident}",
                 json=[{"data": "2026-11-12", "torneo_id": ident,
                        "titolo": "Modern Fall"}])
        event = fetch_event_by_id(cfg, ident)
    assert event.date == dt.date(2026, 11, 12)
    assert event.tournament_id == ident
    assert event.title == "Modern Fall"
    with pytest.raises(ConfigError, match="UUID completo"):
        fetch_event_by_id(cfg, ident.replace("-", ""))
    with responses.RequestsMock() as mock:
        mock.add(responses.GET, f"https://example.test/events?id=eq.{ident}", json=[])
        with pytest.raises(SourceError, match="Torneo non trovato"):
            fetch_event_by_id(cfg, ident)


def test_storia_per_id_fuori_dai_due_giorni(cfg, monkeypatch, tmp_path):
    ident = "92d6beb5-a1e3-44ad-9a65-7c8e982d7e44"
    event = _event(dt.date(2026, 11, 12), ident)
    monkeypatch.setattr(pipelines, "fetch_event_by_id", lambda *_: event)
    monkeypatch.setattr(pipelines, "resolve_date", lambda *_: dt.date(2026, 10, 7))
    context = {}

    def fake_render(_cfg, _template, data, _name, **_kwargs):
        context.update(data)
        return tmp_path / "story.png"

    monkeypatch.setattr(pipelines, "render", fake_render)
    monkeypatch.setattr(pipelines, "story_jpeg", lambda path, *_: path.with_suffix(".jpg"))
    draft = pipelines.story_events_batch(cfg, tournament_id=ident)[0]
    assert draft.meta["phase"] == "evento"
    assert context["fase"] == "evento"
    assert "12 novembre" in context["quando"].lower()
    assert "qr" not in context
    assert context["illustrazione"]["card"] == "Ragavan, Nimble Pilferer"


def test_storia_senza_quota_usa_illustrazione_generale(cfg, monkeypatch, tmp_path):
    ident = "92d6beb5-a1e3-44ad-9a65-7c8e982d7e44"
    event = _event(dt.date(2026, 10, 7), ident)
    event.format = "Premodern"
    cfg.data["content"]["evento"]["quota"] = {}
    monkeypatch.setattr(pipelines, "fetch_event_by_id", lambda *_: event)
    context = {}
    monkeypatch.setattr(pipelines, "render", lambda _cfg, _template, data, *_args, **_kwargs:
                        context.update(data) or tmp_path / "story.png")
    monkeypatch.setattr(pipelines, "story_jpeg", lambda path, *_: path.with_suffix(".jpg"))
    pipelines.story_events_batch(cfg, tournament_id=ident)
    assert context["quota"] == ""
    assert context["illustrazione"]["card"] == "Sarkhan, Fireblood"


def test_cli_rifiuta_id_con_data_o_formato(cfg, monkeypatch):
    ident = "92d6beb5-a1e3-44ad-9a65-7c8e982d7e44"
    monkeypatch.setattr("moma_social.cli.config.load", lambda *_: cfg)
    parser = build_parser()
    for extra in (("--date", "2026-10-07"), ("--format", "Modern")):
        args = parser.parse_args(["stories", "--tournament-id", ident, *extra])
        with pytest.raises(ConfigError, match="non si combina"):
            cmd_post(args)


def test_cli_inoltra_uuid_senza_data(cfg, monkeypatch):
    ident = "92d6beb5-a1e3-44ad-9a65-7c8e982d7e44"
    monkeypatch.setattr("moma_social.cli.config.load", lambda *_: cfg)
    captured = {}

    def fake_generate(_cfg, kind, day, kwargs, args):
        captured.update(kind=kind, day=day, kwargs=kwargs, force=args.force)
        return [("drafted", "1 slide")]

    monkeypatch.setattr("moma_social.cli._genera", fake_generate)
    args = build_parser().parse_args(["stories", "--tournament-id", ident,
                                      "--no-publish", "--force"])
    assert cmd_post(args) == 0
    assert captured == {"kind": "story_event", "day": None,
                        "kwargs": {"tournament_id": ident}, "force": True}


def test_jpeg_reale(tmp_path):
    png = tmp_path / "story.png"
    Image.new("RGB", (2160, 3840), "#14171a").save(png)
    jpg = story_jpeg(png)
    with Image.open(jpg) as image:
        assert image.format == "JPEG"
        assert image.size == (1080, 1920)


@pytest.mark.slow
def test_template_storia_reale_9_16(cfg):
    context = {
        "fase": "domani", "formato": "Premodern",
        "titolo": "Premodern Fall tappa 4",
        "quando": "Mercoledì 14 ottobre · 21:00", "dove": "Uno Critico",
        "quota": "10 €",
        "illustrazione": cfg.data["posts"]["story_event"]["illustrations"]["default"],
    }
    html = build_html(cfg, "storia_evento.html.j2", context)
    assert 'alt="Modena Magic"' in html
    assert 'alt="Uno Critico"' in html
    assert 'class="art-bg"' in html
    assert "object-fit:cover" in html
    assert 'class="art"' not in html
    assert "Link in bio" in html
    assert "Grzegorz Rutkowski" in html
    png = render(cfg, "storia_evento.html.j2", context, "anteprima-storia",
                 size=(1080, 1920), scale=1)
    jpg = story_jpeg(png)
    with Image.open(jpg) as image:
        assert image.format == "JPEG"
        assert image.size == (1080, 1920)


@responses.activate
def test_pubblica_storia_senza_caption_o_coautori(cfg):
    cfg.data["instagram"]["ig_user_id"] = "999"
    cfg.data["instagram"]["access_token"] = "TOKEN"
    cfg.data["instagram"]["collaborators"] = ["uno.critico"]
    api = "https://graph.instagram.com/v21.0"
    responses.post(f"{api}/999/media", json={"id": "CONTAINER"})
    responses.get(f"{api}/CONTAINER", json={"status_code": "FINISHED"})
    responses.post(f"{api}/999/media_publish", json={"id": "STORY"})
    assert InstagramClient(cfg).publish_story("https://host/story.jpg") == "STORY"
    body = responses.calls[0].request.body
    assert "media_type=STORIES" in body
    assert "caption=" not in body
    assert "collaborators=" not in body


@responses.activate
def test_publish_draft_storia_usa_jpeg_e_blocca_doppione(cfg, tmp_path):
    cfg.data["instagram"]["ig_user_id"] = "999"
    cfg.data["instagram"]["access_token"] = "TOKEN"
    cfg.data["media"]["backend"] = "imgbb"
    cfg.data["media"]["imgbb"]["api_key"] = "KEY"
    image = tmp_path / "storia.jpg"
    Image.new("RGB", (1080, 1920), "#14171a").save(image)
    draft = PostDraft(
        kind="story_event", images=[str(image)], caption="",
        meta={"day": "2026-10-07", "phase": "oggi",
              "tournament_id": "92d6beb5-a1e3-44ad-9a65-7c8e982d7e44"},
    )
    responses.post("https://api.imgbb.com/1/upload",
                   json={"data": {"url": "https://host/storia.jpg"}})
    api = "https://graph.instagram.com/v21.0"
    responses.post(f"{api}/999/media", json={"id": "C"})
    responses.get(f"{api}/C", json={"status_code": "FINISHED"})
    responses.post(f"{api}/999/media_publish", json={"id": "STORY"})
    assert publish_draft(cfg, draft)["status"] == "published"
    assert publish_draft(cfg, draft)["status"] == "skipped"
    upload = responses.calls[0].request
    assert b"image/jpeg" in upload.body
    assert len([c for c in responses.calls if c.request.url.endswith("/media_publish")]) == 1
