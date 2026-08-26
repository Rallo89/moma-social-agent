import datetime as dt

from moma_social.captions import build_hashtags, render_caption
from moma_social.repos import events_by_day, fetch_events, fetch_leg_results, fetch_standings


def test_hashtag_deduplicati_e_normalizzati(cfg):
    tokens = build_hashtags(cfg, "weekly_calendar", ["modern", "#mtg", "#Modern"]).split()
    assert tokens[0] == "#magicthegathering"
    assert tokens.count("#mtg") == 1                 # gia' presente fra i base
    assert sum(t.lower() == "#modern" for t in tokens) == 1   # dedup case-insensitive
    assert all(t.startswith("#") for t in tokens)


def test_hashtag_entro_il_limite(cfg):
    cfg.data["content"]["hashtags_max"] = 3
    assert len(build_hashtags(cfg, "weekly_calendar", ["a", "b", "c", "d"]).split()) == 3


def test_caption_calendario(cfg):
    events = fetch_events(cfg, dt.date(2026, 3, 9), dt.date(2026, 3, 15))
    text = render_caption(cfg, "weekly_calendar", {
        "days": events_by_day(events), "periodo": "9 - 15 marzo",
        "events_count": len(events), "formats": ["Modern"], "signup_url": "",
    })
    assert "LUNEDI 9 marzo" in text
    assert "MERCOLEDI 11 marzo" in text
    # Ogni giornata deve restare separata dalla successiva.
    assert "\n\nMERCOLEDI" in text


def test_caption_risultati_cita_il_vincitore(cfg):
    leg = fetch_leg_results(cfg, dt.date(2026, 3, 11))
    standings = fetch_standings(cfg, "Modern")
    text = render_caption(cfg, "leg_results", {
        "leg": leg, "rows": leg.rows[:8], "standings": standings,
        "standings_rows": standings.rows[:10], "next_event_label": "giovedi",
    })
    assert "Marco Bianchi" in text
    assert "CLASSIFICA GENERALE" in text


def test_caption_troncata_al_limite(cfg):
    cfg.data["content"]["caption_max"] = 120
    events = fetch_events(cfg, dt.date(2026, 3, 9), dt.date(2026, 3, 15))
    text = render_caption(cfg, "weekly_calendar", {
        "days": events_by_day(events), "periodo": "9 - 15 marzo",
        "events_count": len(events), "formats": [], "signup_url": "",
    })
    assert len(text) <= 120
    # Il taglio avviene su righe intere, non a meta' parola.
    assert not text.endswith("-")
