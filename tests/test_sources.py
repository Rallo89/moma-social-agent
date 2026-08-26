import json

import pytest

from moma_social.errors import SourceError
from moma_social.sources import (
    _detect_kind,
    _gsheet_csv_url,
    _rows_from_csv,
    _rows_from_json,
    apply_map,
    load_rows,
)


def test_google_sheets_diventa_export_csv():
    url = _gsheet_csv_url("https://docs.google.com/spreadsheets/d/ABC/edit#gid=7")
    assert url == "https://docs.google.com/spreadsheets/d/ABC/export?format=csv&gid=7"


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://x.it/a.csv", "csv"),
        ("https://x.it/a.json", "json"),
        ("postgresql://u@h/db", "sql"),
        ("sqlite:///local.db", "sql"),
        ("https://docs.google.com/spreadsheets/d/A/edit", "csv"),
    ],
)
def test_detect_kind(url, expected):
    assert _detect_kind(url, "auto") == expected


def test_csv_con_punto_e_virgola():
    rows = _rows_from_csv("data;giocatore\n2026-03-11;Marco")
    assert rows == [{"data": "2026-03-11", "giocatore": "Marco"}]


def test_json_con_root_puntato():
    payload = {"result": {"items": [{"a": 1}]}}
    assert _rows_from_json(payload, "result.items") == [{"a": 1}]


def test_json_senza_root_trova_la_lista():
    assert _rows_from_json({"meta": 1, "data": [{"a": 1}]}) == [{"a": 1}]


def test_json_root_inesistente():
    with pytest.raises(SourceError):
        _rows_from_json({"a": 1}, "b.c")


def test_apply_map_traduce_e_conserva_gli_extra():
    rows = apply_map([{"Data": "x", "Note": "y"}], {"date": "Data"})
    assert rows[0]["date"] == "x"
    assert rows[0]["_extra"] == {"Note": "y"}


def test_load_rows_da_file_locale(tmp_path):
    path = tmp_path / "eventi.json"
    path.write_text(json.dumps([{"d": "2026-03-11"}]), encoding="utf-8")
    rows = load_rows({"url": "eventi.json", "map": {"date": "d"}}, tmp_path)
    assert rows[0]["date"] == "2026-03-11"


def test_load_rows_senza_url():
    with pytest.raises(SourceError):
        load_rows({}, ".")


def test_placeholder_sostituiti_nell_url(tmp_path):
    (tmp_path / "2026-03-11.json").write_text('[{"d": "ok"}]', encoding="utf-8")
    rows = load_rows({"url": "{date}.json", "map": {"date": "d"}}, tmp_path,
                     date="2026-03-11")
    assert rows[0]["date"] == "ok"
