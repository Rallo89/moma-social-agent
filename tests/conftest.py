import shutil
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from mtg_social import config  # noqa: E402


@pytest.fixture
def cfg(tmp_path, monkeypatch):
    """Config reale del repo, ma con output e ledger dentro tmp_path."""
    monkeypatch.setattr(config, "project_root", lambda: ROOT)
    loaded = config.load()
    loaded.data["render"]["output_dir"] = str(tmp_path / "out")
    loaded.data["publish"]["ledger"] = str(tmp_path / "published.jsonl")
    return loaded


@pytest.fixture
def sample_dir(tmp_path):
    target = tmp_path / "data"
    shutil.copytree(ROOT / "data" / "samples", target)
    return target
