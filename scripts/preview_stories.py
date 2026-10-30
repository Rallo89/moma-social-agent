"""Sette anteprime con dati fittizi, senza accesso alle sorgenti o pubblicazione.

Eseguire dalla radice: .venv/Scripts/python scripts/preview_stories.py
"""

from PIL import Image, ImageDraw

from moma_social.config import load
from moma_social.render import render
from moma_social.storyutil import story_jpeg


def main():
    cfg = load()
    cfg.data["render"].update(output_dir="out/stories-review", cartella_per_giorno=False)
    formats = ["Pauper", "Modern", "Premodern", "Legacy", "Pioneer", "Limited", "Commander"]
    board = Image.new("RGB", (1620, 2040), "#030617")
    draw = ImageDraw.Draw(board)
    draw.text((24, 12), "ANTEPRIME STORIES - DATI DIMOSTRATIVI", fill="white")
    for i, fmt in enumerate(formats):
        context = {
            "fase": "evento", "formato": fmt,
            "titolo": f"{fmt} Fall 2026 — Tappa 5",
            "data": "Venerdì 30 ottobre", "quando": "Venerdì 30 ottobre 2026 · 21:00",
            "ora": "21:00", "dove": "Uno Critico",
            "quota": "10 €",
            "illustrazione": cfg.section("posts.story_event.illustrations").get(
                fmt.lower(), cfg.section("posts.story_event.illustrations.default")),
        }
        png = render(cfg, "storia_evento.html.j2", context, fmt.lower(),
                     size=(1080, 1920), scale=1)
        story_jpeg(png)
        with Image.open(png) as image:
            assert image.size == (1080, 1920)
            if i < 6:
                x, y = (i % 3) * 540, 50 + (i // 3) * 990
                board.paste(image.resize((540, 960)), (x, y))
                draw.text((x + 12, y + 966), fmt, fill="white")
        print(png, flush=True)
    board.save(cfg.resolve_path("out/stories-review/confronto.jpg"), quality=95)


if __name__ == "__main__":
    main()
