"""Rendering HTML -> PNG.

I template sono HTML+CSS con Jinja2: il modo piu' pratico per riprodurre un
template grafico fornito dal grafico (PNG/JPG di sfondo + testo sovrapposto)
mantenendo tutto versionato e diffabile.

Due backend, stessa interfaccia:
  * "chromium"   -> chrome headless --screenshot (nessuna dipendenza Python)
  * "playwright" -> piu' controllo (attesa font, clip), se installato
"""

from __future__ import annotations

import base64
import mimetypes
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from jinja2 import Environment, FileSystemLoader, StrictUndefined, select_autoescape

from .config import Config
from .errors import RenderError
from .pngutil import crop_top_left
from .timeutil import fmt_date, resolve_date, weekday_it

# Nomi cercati nel PATH. msedge c'e' sempre su Windows ed e' Chromium:
# per fare uno screenshot va bene quanto Chrome.
CHROMIUM_NAMES = (
    "chromium", "chromium-browser", "google-chrome", "google-chrome-stable",
    "chrome", "msedge", "microsoft-edge",
)


def _installed_browsers() -> list[Path]:
    """Percorsi tipici dei browser, per sistema operativo.

    Su Windows e macOS i browser non stanno nel PATH: senza questa lista
    l'agente sarebbe inutilizzabile fuori da Linux, dove invece funziona.
    """
    if sys.platform == "win32":
        radici = [
            os.environ.get("ProgramFiles", r"C:\Program Files"),
            os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
            os.environ.get("LOCALAPPDATA", ""),
        ]
        relativi = [
            r"Google\Chrome\Application\chrome.exe",
            r"Chromium\Application\chrome.exe",
            r"Microsoft\Edge\Application\msedge.exe",
        ]
        return [Path(radice) / rel
                for radice in radici if radice
                for rel in relativi]
    if sys.platform == "darwin":
        return [
            Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"),
            Path("/Applications/Chromium.app/Contents/MacOS/Chromium"),
            Path("/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
        ]
    return [Path("/usr/bin/chromium"), Path("/usr/bin/chromium-browser"),
            Path("/usr/bin/google-chrome")]


# ── Jinja ───────────────────────────────────────────────────────────────────
def _asset_data_uri(root: Path, relative: str) -> str:
    """Inlina un asset come data URI: il PNG resta autonomo, niente path rotti.

    Totale per costruzione: input vuoto, path inesistente o cartella
    restituiscono stringa vuota, cosi' i template possono chiamare il filtro
    senza doversi proteggere prima.
    """
    if not relative:
        return ""
    path = Path(relative)
    if not path.is_absolute():
        path = root / path
    if not path.is_file():
        return ""
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode()}"


def image_env(cfg: Config) -> Environment:
    env = Environment(
        loader=FileSystemLoader(cfg.root / "templates" / "images"),
        autoescape=select_autoescape(["html", "xml"]),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    env.filters["asset"] = lambda rel: _asset_data_uri(cfg.root, rel)
    env.filters["data"] = fmt_date
    env.filters["giorno"] = weekday_it
    return env


def post_size(cfg: Config, kind: str = "") -> tuple[int, int]:
    """Dimensione della slide: quella del post se indicata, altrimenti globale.

    Serve perche' i template grafici non hanno tutti lo stesso formato: il
    feed Instagram accetta 1:1 e 4:5, e un'associazione puo' avere il
    calendario in verticale e la classifica in quadrato.
    """
    width = cfg.get(f"posts.{kind}.width") or cfg.get("render.width", 1080)
    height = cfg.get(f"posts.{kind}.height") or cfg.get("render.height", 1350)
    return int(width), int(height)


def build_html(cfg: Config, template: str, context: dict) -> str:
    env = image_env(cfg)
    # Undefined e' strict: ogni variabile usata dal layout base deve esistere
    # sempre, anche quando il template concreto non la valorizza.
    base = {
        "brand": cfg.section("brand"),
        "org": cfg.section("org"),
        "width": cfg.get("render.width", 1080),
        "height": cfg.get("render.height", 1350),
        "background": "",
        "density": "",
        "row_style": "strip",
    }
    return env.get_template(template).render({**base, **context})


# ── Screenshot ──────────────────────────────────────────────────────────────
def _find_chromium(configured: str = "") -> str:
    """Percorso di un browser Chromium: configurato, nel PATH, o installato."""
    if configured:
        if Path(configured).exists():
            return configured
        raise RenderError(f"chromium_path configurato ma inesistente: {configured}")

    for name in CHROMIUM_NAMES:
        found = shutil.which(name)
        if found:
            return found

    for candidato in _installed_browsers():
        if candidato.is_file():
            return str(candidato)

    # Browser installati da Playwright (anche quello di Claude Code sul web)
    pw_root = Path(os.environ.get("PLAYWRIGHT_BROWSERS_PATH", "")
                   or Path.home() / ".cache/ms-playwright")
    if pw_root.exists():
        for candidate in sorted(pw_root.glob("chromium*/chrome-linux/chrome")):
            return str(candidate)
        mac_glob = "chromium*/chrome-mac/Chromium.app/Contents/MacOS/Chromium"
        for candidate in sorted(pw_root.glob(mac_glob)):
            return str(candidate)
        for candidate in sorted(pw_root.glob("chromium*/chrome-win/chrome.exe")):
            return str(candidate)

    raise RenderError(
        "Nessun browser Chromium trovato. Installa Google Chrome (su Windows va "
        "bene anche Microsoft Edge, gia' presente), oppure indica l'eseguibile "
        "in render.chromium_path dentro config/config.toml."
    )


def _shot_chromium(cfg: Config, html: str, out_path: Path,
                   size: tuple[int, int]) -> Path:
    binary = _find_chromium(cfg.get("render.chromium_path", ""))
    width, height = size
    scale = cfg.get("render.scale", 2)

    # In headless la finestra riserva spazio alla UI del browser: il viewport
    # e' piu' basso di --window-size e l'ultima fascia della slide resterebbe
    # non dipinta. Si chiede una finestra abbondante e si ritaglia dopo.
    margin = 240

    with tempfile.TemporaryDirectory() as tmp:
        page = Path(tmp) / "page.html"
        page.write_text(html, encoding="utf-8")
        cmd = [
            binary, "--headless", "--disable-gpu", "--no-sandbox",
            "--hide-scrollbars", "--force-color-profile=srgb",
            "--font-render-hinting=none", "--disable-dev-shm-usage",
            f"--user-data-dir={Path(tmp) / 'profile'}",
            f"--window-size={width},{height + margin}",
            f"--force-device-scale-factor={scale}",
            "--virtual-time-budget=4000",
            f"--screenshot={out_path}",
            page.as_uri(),
        ]
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise RenderError(
            f"Screenshot fallito (exit {proc.returncode}).\n{proc.stderr[-1500:]}"
        )
    return crop_top_left(out_path, width * scale, height * scale)


def _shot_playwright(cfg: Config, html: str, out_path: Path,
                     size: tuple[int, int]) -> Path:
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as exc:  # pragma: no cover
        raise RenderError("backend 'playwright' scelto ma pacchetto non installato") from exc
    width, height = size
    with sync_playwright() as pw:
        browser = pw.chromium.launch(args=["--no-sandbox"])
        page = browser.new_page(
            viewport={"width": width, "height": height},
            device_scale_factor=cfg.get("render.scale", 2),
        )
        page.set_content(html, wait_until="networkidle")
        page.wait_for_timeout(200)
        page.screenshot(path=str(out_path))
        browser.close()
    return out_path


def render(cfg: Config, template: str, context: dict, out_name: str,
           size: tuple[int, int] | None = None) -> Path:
    """Renderizza un template immagine e restituisce il path del PNG."""
    size = size or (cfg.get("render.width", 1080), cfg.get("render.height", 1350))
    context = {**context, "width": size[0], "height": size[1]}
    html = build_html(cfg, template, context)
    out_dir = cfg.resolve_path(cfg.get("render.output_dir", "out"))
    if cfg.get("render.cartella_per_giorno", True):
        # Una cartella per lancio: il giorno in cui l'agente ha girato, non
        # quello dell'evento. Rigenerare una settimana vecchia non si mescola
        # con l'ultimo giro, e per capire cosa e' uscito oggi basta la data.
        out_dir = out_dir / resolve_date("today", cfg.timezone).isoformat()
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / (out_name if out_name.endswith(".png") else f"{out_name}.png")

    # L'HTML resta accanto al PNG: e' l'artefatto da aprire per capire un
    # rendering venuto male, senza rilanciare la pipeline.
    out_path.with_suffix(".html").write_text(html, encoding="utf-8")

    backend = cfg.get("render.backend", "chromium")
    if backend == "playwright":
        return _shot_playwright(cfg, html, out_path, size)
    return _shot_chromium(cfg, html, out_path, size)
