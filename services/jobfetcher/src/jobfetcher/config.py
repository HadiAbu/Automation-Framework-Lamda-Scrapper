from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

BOARD_TYPES = ("greenhouse", "lever")
DEFAULT_PATH = Path(__file__).with_name("boards.json")


@dataclass(frozen=True)
class BoardConfig:
    type: str
    name: str


@dataclass(frozen=True)
class Config:
    boards: tuple[BoardConfig, ...]
    keywords: tuple[str, ...]


def load_config(path: Path | None = None) -> Config:
    data = json.loads((path or DEFAULT_PATH).read_text(encoding="utf-8"))
    boards = []
    for entry in data["boards"]:
        if entry["type"] not in BOARD_TYPES:
            raise ValueError(
                f"unknown board type {entry['type']!r}; expected one of {BOARD_TYPES}"
            )
        boards.append(BoardConfig(entry["type"], entry["name"]))
    if not boards:
        raise ValueError("config has no boards")
    keywords = tuple(k.lower() for k in data.get("keywords", []))
    return Config(tuple(boards), keywords)
