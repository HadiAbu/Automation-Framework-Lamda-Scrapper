from __future__ import annotations

from abc import ABC, abstractmethod

from jobfetcher.http import HttpGet
from jobfetcher.models import JobPost


class JobSource(ABC):
    """Strategy for one job-board API; subclasses set `kind` and implement `fetch`."""

    kind: str = ""

    def __init__(self, name: str, http_get: HttpGet) -> None:
        self.name = name
        self._http_get = http_get

    @property
    def label(self) -> str:
        return f"{self.kind}:{self.name}"

    @abstractmethod
    def fetch(self) -> list[JobPost]: ...
