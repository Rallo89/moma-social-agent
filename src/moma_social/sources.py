"""Adapter sorgenti dati.

Una sola funzione pubblica, `load_rows`, che normalizza in `list[dict]`
qualunque cosa ci venga fornita:

  * HTTP JSON      -> https://api.esempio.it/eventi?from={date_from}
  * HTTP CSV       -> https://esempio.it/export.csv
  * Google Sheets  -> link normale al foglio (convertito in export CSV)
  * SQL            -> postgresql://... / mysql://... / sqlite:///...
  * File locale    -> data/samples/events.json (json | csv | yaml)

I placeholder {date_from} {date_to} {date} {format} {season} vengono
sostituiti in url, params, headers e query: se il DB supporta il filtro
server-side lo usa, altrimenti il filtro viene comunque riapplicato in
memoria dai repository (vedi repos.py). Nessuna assunzione sullo schema
remoto: la traduzione dei nomi colonna sta nella sezione [.map] della config.
"""

from __future__ import annotations

import csv
import io
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

import requests
import yaml

from .errors import SourceError

TIMEOUT = 30
GSHEET_RE = re.compile(r"https://docs\.google\.com/spreadsheets/d/([\w-]+)")
SQL_SCHEMES = ("postgresql", "postgres", "mysql", "mysql+pymysql", "sqlite", "mssql")


class _SafeDict(dict):
    """format_map che lascia intatti i placeholder sconosciuti."""

    def __missing__(self, key):  # noqa: D105
        return "{" + key + "}"


def _fill(value: Any, params: dict) -> Any:
    if isinstance(value, str):
        return value.format_map(_SafeDict(params))
    if isinstance(value, dict):
        return {k: _fill(v, params) for k, v in value.items()}
    if isinstance(value, list):
        return [_fill(v, params) for v in value]
    return value


def _gsheet_csv_url(url: str) -> str:
    """Trasforma un link a Google Sheets nel suo export CSV."""
    sheet_id = GSHEET_RE.match(url).group(1)
    gid = parse_qs(urlparse(url).fragment).get("gid", ["0"])[0]
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/export?format=csv&gid={gid}"


def _detect_kind(url: str, declared: str, content_type: str = "") -> str:
    if declared and declared != "auto":
        return declared
    scheme = urlparse(url).scheme
    if scheme in SQL_SCHEMES or url.startswith("sqlite"):
        return "sql"
    if GSHEET_RE.match(url):
        return "csv"
    lowered = url.split("?")[0].lower()
    for ext, kind in ((".json", "json"), (".csv", "csv"), (".tsv", "csv"),
                      (".yaml", "yaml"), (".yml", "yaml")):
        if lowered.endswith(ext):
            return kind
    if "json" in content_type:
        return "json"
    if "csv" in content_type:
        return "csv"
    return "json"


def _rows_from_json(payload: Any, root: str = "") -> list[dict]:
    """Estrae la lista di record, seguendo `root` puntato se indicato."""
    node = payload
    for part in filter(None, root.split(".")):
        if not isinstance(node, dict) or part not in node:
            raise SourceError(f"Chiave '{root}' non trovata nella risposta JSON")
        node = node[part]
    if isinstance(node, list):
        return [r for r in node if isinstance(r, dict)]
    if isinstance(node, dict):
        # Nessun root indicato: cerca la prima lista di oggetti utile.
        for value in node.values():
            if isinstance(value, list) and (not value or isinstance(value[0], dict)):
                return value
        return [node]
    raise SourceError("La risposta JSON non contiene una lista di record")


def _rows_from_csv(text: str) -> list[dict]:
    sample = text[:4096]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
    except csv.Error:
        dialect = csv.excel
    reader = csv.DictReader(io.StringIO(text), dialect=dialect)
    return [{(k or "").strip(): v for k, v in row.items()} for row in reader]


def _fetch_http(url: str, spec: dict, params: dict) -> list[dict]:
    if GSHEET_RE.match(url):
        url = _gsheet_csv_url(url)
    query = _fill(spec.get("params", {}), params)
    headers = _fill(spec.get("headers", {}), params)
    try:
        response = requests.get(url, params=query or None, headers=headers or None,
                                timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise SourceError(f"Sorgente non raggiungibile ({url}): {exc}") from exc

    if response.status_code >= 400:
        # Un 401 non e' "irraggiungibile": e' una chiave sbagliata, e il corpo
        # della risposta di solito lo dice. Va riportato, altrimenti si perde
        # l'unica informazione utile.
        raise SourceError(
            f"La sorgente ha risposto {response.status_code} ({url}): "
            f"{response.text[:300]}"
        )

    kind = _detect_kind(url, spec.get("kind", "auto"),
                        response.headers.get("content-type", ""))
    if kind == "csv":
        return _rows_from_csv(response.text)
    if kind == "yaml":
        return _rows_from_json(yaml.safe_load(response.text), spec.get("root", ""))
    try:
        payload = response.json()
    except ValueError as exc:
        raise SourceError(f"Risposta non JSON da {url}: {response.text[:200]!r}") from exc
    return _rows_from_json(payload, spec.get("root", ""))


def _fetch_sql(url: str, spec: dict, params: dict) -> list[dict]:
    query = spec.get("query")
    if not query:
        raise SourceError("Sorgente SQL senza 'query' in configurazione")
    try:
        from sqlalchemy import create_engine, text
    except ImportError as exc:  # pragma: no cover - dipende dall'installazione
        raise SourceError("Sorgente SQL richiede SQLAlchemy: pip install '.[sql]'") from exc

    # I placeholder diventano bind parameters (:date_from), non concatenazione:
    # nessun valore esterno finisce mai dentro il testo della query.
    bound = re.sub(r"\{(\w+)\}", r":\1", query)
    try:
        engine = create_engine(url)
        with engine.connect() as conn:
            result = conn.execute(text(bound), params)
            return [dict(row) for row in result.mappings()]
    except Exception as exc:  # noqa: BLE001 - qualunque errore driver
        raise SourceError(f"Query SQL fallita: {exc}") from exc


def _fetch_file(path: Path, spec: dict) -> list[dict]:
    if not path.exists():
        raise SourceError(f"File sorgente non trovato: {path}")
    text = path.read_text(encoding="utf-8")
    kind = _detect_kind(str(path), spec.get("kind", "auto"))
    if kind == "csv":
        return _rows_from_csv(text)
    if kind == "yaml":
        return _rows_from_json(yaml.safe_load(text), spec.get("root", ""))
    return _rows_from_json(json.loads(text), spec.get("root", ""))


def apply_map(rows: list[dict], mapping: dict[str, str]) -> list[dict]:
    """Traduce i nomi colonna della sorgente nei campi del modello interno.

    I campi non mappati restano disponibili in `_extra`, cosi' un template
    puo' usarli senza bisogno di toccare il codice.
    """
    if not mapping:
        return [dict(row, _extra=dict(row)) for row in rows]
    out = []
    for row in rows:
        mapped = {target: row.get(source) for target, source in mapping.items()
                  if source in row}
        used = set(mapping.values())
        mapped["_extra"] = {k: v for k, v in row.items() if k not in used}
        out.append(mapped)
    return out


def load_rows(spec: dict, base_dir: Path, **params) -> list[dict]:
    """Carica e normalizza i record di una sorgente configurata."""
    url = (spec.get("url") or "").strip()
    if not url:
        raise SourceError("Sorgente senza 'url' in configurazione")
    url = _fill(url, params)

    scheme = urlparse(url).scheme
    if scheme in ("http", "https"):
        rows = _fetch_http(url, spec, params)
    elif _detect_kind(url, spec.get("kind", "auto")) == "sql":
        rows = _fetch_sql(url, spec, params)
    else:
        path = Path(url.removeprefix("file://"))
        rows = _fetch_file(path if path.is_absolute() else base_dir / path, spec)

    return apply_map(rows, spec.get("map", {}))


def describe_postgrest(base_url: str, headers: dict | None = None) -> dict[str, list[str]]:
    """Tabelle e colonne esposte da un endpoint PostgREST (Supabase).

    La radice di PostgREST restituisce la descrizione OpenAPI dello schema:
    e' il modo di scoprire come si chiamano davvero le colonne senza
    trascriverle a mano dalla dashboard.
    """
    url = base_url.rstrip("/") + "/"
    try:
        response = requests.get(url, headers=headers or None, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise SourceError(f"Endpoint non raggiungibile ({url}): {exc}") from exc
    if response.status_code >= 400:
        raise SourceError(
            f"L'endpoint ha risposto {response.status_code}: {response.text[:300]}"
        )
    try:
        spec = response.json()
    except ValueError as exc:
        raise SourceError(
            f"La radice non ha restituito una descrizione OpenAPI: {response.text[:200]}"
        ) from exc

    definizioni = spec.get("definitions") or spec.get("components", {}).get("schemas", {})
    if not definizioni:
        raise SourceError("Nessuna tabella descritta dall'endpoint")
    return {
        tabella: sorted((corpo.get("properties") or {}).keys())
        for tabella, corpo in sorted(definizioni.items())
    }
