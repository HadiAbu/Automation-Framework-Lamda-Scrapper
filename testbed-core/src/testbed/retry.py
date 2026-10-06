from __future__ import annotations

import pytest
from _pytest.runner import runtestprotocol

from testbed.reporting.collector import FIRST_FAILURE_KEY, FLAKY_KEY, MAX_MESSAGE


def _failed_call(reports: list[pytest.TestReport]) -> pytest.TestReport | None:
    return next((r for r in reports if r.when == "call" and r.failed), None)


def run_with_retries(item: pytest.Item, nextitem: pytest.Item | None, retries: int) -> bool:
    ihook = item.ihook
    ihook.pytest_runtest_logstart(nodeid=item.nodeid, location=item.location)

    # runtestprotocol re-initialises the fixture request itself on a re-run.
    reports = runtestprotocol(item, nextitem=nextitem, log=False)
    first_failure: str | None = None
    attempts = 0
    while attempts < retries and (failed := _failed_call(reports)) is not None:
        if first_failure is None:
            first_failure = failed.longreprtext[:MAX_MESSAGE]
        attempts += 1
        reports = runtestprotocol(item, nextitem=nextitem, log=False)

    if first_failure is not None and _failed_call(reports) is None:
        call = next((r for r in reports if r.when == "call"), None)
        if call is not None and call.passed:
            call.user_properties.append((FLAKY_KEY, "1"))
            call.user_properties.append((FIRST_FAILURE_KEY, first_failure))

    for report in reports:
        ihook.pytest_runtest_logreport(report=report)
    ihook.pytest_runtest_logfinish(nodeid=item.nodeid, location=item.location)
    return True
