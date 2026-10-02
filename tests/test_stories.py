"""Storie: un URL per torneo, due fasi e pubblicazione senza feed."""

import datetime as dt
from pathlib import Path

import pytest
import responses
from PIL import Image

from moma_social import pipelines
from moma_social.instagram import InstagramClient
from moma_social.models import Event, PostDraft
from moma_social.publish import dedupe_key, publish_draft
from moma_social.render import render
from moma_social.storyutil import qr_data_uri, story_jpeg


def _event(day, ident, title="Modern Fall"):
    return Event(
        date=day, tournament_id=ident, title=title, format="Modern",
        venue="Uno Critico", signup_url=f"https://modena-magic.vercel.app/tornei/{ident}",
    )


def test_due_storie_per_due_giorni_e_tornei_distinti(cfg, monkeypatch, tmp_path):
    today = dt.date(2026, 10, 7)
    first = "92d6beb5-a1e3-44ad-9a65-7c8e982d7e44"
    second = "161dd0a4-997a-493d-a2b6-5d85186687f8"
    events = [_event(today, first), _event(today, second, "Modern Extra"),
              _event(today + dt.timedelta(days=1), first)]
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
    assert contexts[0][1]["qr"] != contexts[1][1]["qr"]


def test_url_sbagliato_salta_solo_quel_torneo(cfg, monkeypatch, tmp_path):
    day = dt.date(2026, 10, 7)
    ident = "92d6beb5-a1e3-44ad-9a65-7c8e982d7e44"
    invalid = _event(day, ident)
    invalid.signup_url = "https://modena-magic.vercel.app/tornei/altro"
    valid = _event(day, "161dd0a4-997a-493d-a2b6-5d85186687f8")
    monkeypatch.setattr(pipelines, "fetch_events", lambda *_: [invalid, valid])
    monkeypatch.setattr(pipelines, "render", lambda *args, **kwargs: tmp_path / "story.png")
    monkeypatch.setattr(pipelines, "story_jpeg", lambda path, *_: path.with_suffix(".jpg"))
    with pytest.warns(UserWarning, match="Storia saltata"):
        drafts = pipelines.story_events_batch(cfg, day)
    assert len(drafts) == 1
    assert drafts[0].meta["tournament_id"] == valid.tournament_id


def test_qr_e_jpeg_reali(tmp_path):
    uri = qr_data_uri("https://modena-magic.vercel.app/tornei/abc")
    assert uri.startswith("data:image/png;base64,")
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
        "qr": qr_data_uri("https://modena-magic.vercel.app/tornei/abc"),
    }
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
