"""Generazione delle caption dai template testuali."""

from __future__ import annotations

from jinja2 import Environment, FileSystemLoader, StrictUndefined

from .config import Config
from .models import event_label, format_fee
from .timeutil import fmt_date, fmt_range, weekday_it


def caption_env(cfg: Config) -> Environment:
    env = Environment(
        loader=FileSystemLoader(cfg.root / "templates" / "captions"),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
    )
    env.filters["data"] = fmt_date
    env.filters["giorno"] = weekday_it
    # "10.00" a database, "10 €" ovunque si legga.
    env.filters["quota"] = format_fee
    # Lo stesso nome che va sulla grafica, e la stessa ora di ripiego.
    env.filters["etichetta"] = lambda evento: event_label(
        evento,
        cfg.get("content.evento.titolo_tappa", "Tappa {stage}"),
        cfg.get("content.evento.titolo_finale", "Finale"),
    )
    env.filters["ora"] = lambda evento: (
        evento.start_time or cfg.get("content.evento.ora_default", ""))
    env.globals["periodo"] = fmt_range
    return env


def build_hashtags(cfg: Config, kind: str, extra: list[str] | None = None) -> str:
    """Base + specifici del post + dinamici, deduplicati e sotto il limite IG."""
    tags: list[str] = []
    for group in (cfg.get("content.hashtags_base", []),
                  cfg.get(f"posts.{kind}.hashtags", []),
                  extra or []):
        for tag in group:
            tag = tag.strip()
            if not tag:
                continue
            tag = tag if tag.startswith("#") else f"#{tag}"
            if tag.lower() not in {t.lower() for t in tags}:
                tags.append(tag)
    return " ".join(tags[: cfg.get("content.hashtags_max", 20)])


def render_caption(cfg: Config, kind: str, context: dict,
                   extra_hashtags: list[str] | None = None) -> str:
    template_name = cfg.require(f"posts.{kind}.caption_template")
    env = caption_env(cfg)
    text = env.get_template(template_name).render(
        org=cfg.section("org"),
        hashtags=build_hashtags(cfg, kind, extra_hashtags),
        **context,
    )
    text = "\n".join(line.rstrip() for line in text.strip().splitlines())

    limit = cfg.get("content.caption_max", 2200)
    if len(text) > limit:
        # Taglio all'ultima riga intera che ci sta: meglio una caption piu'
        # corta che una troncata a meta' parola.
        keep, total = [], 0
        for line in text.splitlines():
            if total + len(line) + 1 > limit - 1:
                break
            keep.append(line)
            total += len(line) + 1
        text = "\n".join(keep).rstrip()
    return text
