from __future__ import annotations

from jobfetcher.config import BoardConfig
from jobfetcher.http import HttpGet
from jobfetcher.sources.base import JobSource
from jobfetcher.sources.greenhouse import GreenhouseSource
from jobfetcher.sources.lever import LeverSource

SOURCE_TYPES: dict[str, type[JobSource]] = {
    "greenhouse": GreenhouseSource,
    "lever": LeverSource,
}


def create_source(board: BoardConfig, http_get: HttpGet) -> JobSource:
    return SOURCE_TYPES[board.type](board.name, http_get)
