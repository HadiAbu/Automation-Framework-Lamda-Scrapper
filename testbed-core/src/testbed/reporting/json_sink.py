from __future__ import annotations

import json
from pathlib import Path

from testbed.ports import ReportSink
from testbed.reporting.models import RunReport


class JsonSink(ReportSink):
    def __init__(self, directory: Path) -> None:
        self._directory = Path(directory)

    def publish(self, report: RunReport) -> str:
        self._directory.mkdir(parents=True, exist_ok=True)
        path = self._directory / "report.json"
        path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
        return str(path)
