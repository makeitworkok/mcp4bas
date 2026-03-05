from __future__ import annotations

from pathlib import Path

from mcp4bas.prompts import PROMPT_ASSETS
from mcp4bas.resources import RESOURCE_ASSETS


ROOT = Path(__file__).resolve().parents[1] / "src" / "mcp4bas"


def test_prompt_assets_are_consistent() -> None:
    names = [asset["name"] for asset in PROMPT_ASSETS]
    assert len(names) == len(set(names))

    for asset in PROMPT_ASSETS:
        assert asset["description"].strip()
        file_path = ROOT / asset["path"]
        assert file_path.exists()


def test_resource_assets_are_consistent() -> None:
    names = [asset["name"] for asset in RESOURCE_ASSETS]
    assert len(names) == len(set(names))

    for asset in RESOURCE_ASSETS:
        assert asset["description"].strip()
        file_path = ROOT / asset["path"]
        assert file_path.exists()
