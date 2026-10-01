import datetime as dt

from moma_social.captions import build_hashtags, render_caption
from moma_social.repos import events_by_day, fetch_events, fetch_leg_results


def test_hashtag_deduplicati_e_normalizzati(cfg):
    tokens = build_hashtags(cfg, "weekly_calendar", ["modern", "#mtg", "#Modern"]).split()
    assert tokens[0] == cfg.get("content.hashtags_base")[0]
    assert "#magicthegathering" in tokens
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
    assert "LUNEDÌ 9 marzo" in text
    assert "MERCOLEDÌ 11 marzo" in text
    # Ogni giornata deve restare separata dalla successiva.
    assert "\n\nMERCOLEDÌ" in text


def test_caption_mensile_raggruppa_formati_e_conserva_la_chiusura(cfg):
    from moma_social.pipelines import _gruppi_mensili

    events = fetch_events(cfg, dt.date(2026, 3, 1), dt.date(2026, 3, 31))
    gruppi = _gruppi_mensili(cfg, events)
    text = render_caption(cfg, "monthly_calendar", {
        "gruppi": gruppi, "mese": "marzo 2026", "periodo": "marzo 2026",
        "events_count": len(events), "formats": [g["formato"] for g in gruppi],
        "signup_url": cfg.get("content.evento.link"),
    })
    assert text.index("👑 COMMANDER") < text.index("🎁 LIMITED")
    assert text.index("🎁 LIMITED") < text.index("⚡ MODERN")
    assert "14/03 15:00 Prerelease" in text
    assert "15/03 16:00 Draft domenicale" in text
    assert "Iscrizioni e regolamenti:" in text
    assert "Ci vediamo ai tavoli! 🔥" in text


def test_caption_risultati_cita_il_vincitore(cfg):
    leg = fetch_leg_results(cfg, dt.date(2026, 3, 11))
    meta = [{"nome": "Boros Energy", "percento": 25},
            {"nome": "Izzet Murktide", "percento": 17}]
    text = render_caption(cfg, "leg_results", {
        "leg": leg, "rows": leg.rows[:8], "meta": meta,
        "next_event_label": "giovedi",
    })
    assert "Marco Bianchi" in text
    assert "IL META DELLA SERATA" in text
    assert "Boros Energy — 25%" in text


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


def test_caption_dichiara_il_pari_merito(cfg):
    """Due giocatori a pari punti: dichiararne uno solo vincitore e' scorretto."""
    import datetime as d

    from moma_social.models import LegResults, ResultRow

    leg = LegResults(
        date=d.date(2026, 9, 3), format="Modern", leg="Tappa 5", players_count=12,
        rows=[ResultRow(rank=1, player="Tianguang Liu", points=10, record="3-0-1"),
              ResultRow(rank=2, player="Marco Bianchi", points=10, record="3-0-1"),
              ResultRow(rank=3, player="Luca Nobili", points=9)],
    )
    testo = render_caption(cfg, "leg_results", {
        "leg": leg, "rows": leg.rows, "meta": [],
        "next_event_label": "mercoledi",
    })
    assert "pari punti" in testo
    assert "Tianguang Liu e Marco Bianchi" in testo
    assert "Vince Tianguang Liu" not in testo


def test_caption_vincitore_unico(cfg):
    import datetime as d

    from moma_social.models import LegResults, ResultRow

    leg = LegResults(
        date=d.date(2026, 9, 3), format="Modern", leg="Tappa 5",
        rows=[ResultRow(rank=1, player="Primo", points=12, deck="Boros", record="4-0"),
              ResultRow(rank=2, player="Secondo", points=9)],
    )
    testo = render_caption(cfg, "leg_results", {
        "leg": leg, "rows": leg.rows, "meta": [],
        "next_event_label": "mercoledi",
    })
    assert "Vince Primo con Boros (4-0)" in testo
    assert "pari punti" not in testo


def test_caption_formato_quota_link_e_orario(cfg):
    """La caption deve dire le stesse cose della grafica, scritte uguale."""
    import datetime as d
    import json
    import tempfile
    from pathlib import Path

    from moma_social.pipelines import format_spotlight

    righe = [{"data": "2026-09-10", "titolo": "Modern Fall tappa 2",
              "formato": "Modern", "lega": "Modern Fall 2026",
              "sede": "Uno Critico", "quota": 10.0}]
    f = Path(tempfile.mkdtemp()) / "e.json"
    f.write_text(json.dumps(righe), encoding="utf-8")
    cfg.data["sources"]["events"] = {"url": str(f), "kind": "json", "map": {
        "date": "data", "title": "titolo", "format": "formato",
        "venue": "sede", "entry_fee": "quota", "league": "lega"}}

    testo = format_spotlight(cfg, d.date(2026, 9, 10)).caption
    assert "10 €" in testo and "10.0" not in testo    # non la cifra grezza
    assert "Modern Fall 2026 · Tappa 2" in testo      # come sulla grafica
    assert "Inizio 21:00" in testo                    # ora di ripiego, come la card
    assert cfg.get("content.evento.link") in testo    # non "link in bio"
