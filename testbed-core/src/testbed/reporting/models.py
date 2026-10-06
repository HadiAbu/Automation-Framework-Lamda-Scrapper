from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from typing import Any, Literal

Outcome = Literal["passed", "failed", "skipped", "flaky"]


@dataclass(frozen=True)
class CaseResult:
    nodeid: str
    project: str | None
    outcome: Outcome
    duration: float
    message: str | None = None


@dataclass
class RunReport:
    started_at: datetime
    duration: float
    results: list[CaseResult] = field(default_factory=list)

    def count(self, outcome: Outcome) -> int:
        return sum(1 for r in self.results if r.outcome == outcome)

    def summary(self) -> dict[str, int]:
        return {
            "total": len(self.results),
            "passed": self.count("passed"),
            "failed": self.count("failed"),
            "skipped": self.count("skipped"),
            "flaky": self.count("flaky"),
        }

    @property
    def ok(self) -> bool:
        return self.count("failed") == 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "started_at": self.started_at.isoformat(),
            "duration": round(self.duration, 3),
            "summary": self.summary(),
            "results": [asdict(r) for r in self.results],
        }
