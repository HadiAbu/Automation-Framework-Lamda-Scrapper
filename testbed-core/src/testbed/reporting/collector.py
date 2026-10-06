from __future__ import annotations

import time
from datetime import datetime, timezone
from typing import Any

import pytest

from testbed.ports import ReportSink
from testbed.reporting.models import CaseResult, Outcome, RunReport

PROJECT_KEY = "testbed_project"
FLAKY_KEY = "testbed_flaky"
FIRST_FAILURE_KEY = "testbed_first_failure"
MAX_MESSAGE = 2000


class ReportCollector:
    """Pytest plugin object: turns test reports into a RunReport and publishes it."""

    def __init__(self, sink: ReportSink, *, is_worker: bool = False) -> None:
        self._sink = sink
        self._is_worker = is_worker
        self._results: list[CaseResult] = []
        self._started_at = datetime.now(timezone.utc)
        self._t0 = time.monotonic()
        self.location: str | None = None

    def pytest_runtest_logreport(self, report: pytest.TestReport) -> None:
        result = self._to_result(report)
        if result is not None:
            self._results.append(result)

    def pytest_sessionfinish(self, session: Any) -> None:
        if self._is_worker:
            return
        self.location = self._sink.publish(self.build())

    def pytest_terminal_summary(self, terminalreporter: Any) -> None:
        if self.location:
            terminalreporter.write_sep("-", f"testbed report: {self.location}")

    def build(self) -> RunReport:
        return RunReport(
            started_at=self._started_at,
            duration=time.monotonic() - self._t0,
            results=list(self._results),
        )

    @staticmethod
    def _to_result(report: pytest.TestReport) -> CaseResult | None:
        recorded = (
            report.when == "call"
            or (report.when == "setup" and not report.passed)
            or (report.when == "teardown" and report.failed)
        )
        if not recorded:
            return None
        nodeid = report.nodeid
        if report.when == "teardown":
            # A teardown error is its own failed entry so RunReport.ok matches pytest's exit status.
            nodeid = f"{nodeid} [teardown]"
        props = dict(report.user_properties)
        outcome: Outcome = report.outcome  # type: ignore[assignment]
        message: str | None = None
        if outcome == "failed":
            message = report.longreprtext[:MAX_MESSAGE]
        elif outcome == "skipped" and isinstance(report.longrepr, tuple):
            message = str(report.longrepr[2])
        elif outcome == "passed" and FLAKY_KEY in props:
            outcome = "flaky"
            message = props.get(FIRST_FAILURE_KEY)
        return CaseResult(
            nodeid=nodeid,
            project=props.get(PROJECT_KEY),
            outcome=outcome,
            duration=report.duration,
            message=message,
        )
