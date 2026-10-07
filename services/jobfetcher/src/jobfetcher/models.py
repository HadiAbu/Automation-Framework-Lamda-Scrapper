from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class JobPost:
    id: str
    source: str
    company: str
    title: str
    location: str
    url: str
    posted_at: str | None
    description: str
    matched_keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceResult:
    name: str
    ok: bool
    jobs: list[JobPost] = field(default_factory=list)
    error: str | None = None

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "count": len(self.jobs),
            "error": self.error,
        }
