from __future__ import annotations

import pytest

from testbed.config import report_dir
from testbed.discovery import resolve_project_name
from testbed.fixtures import (  # noqa: F401
    adapter,
    artifact_dir,
    aws_session,
    client,
    env_config,
    registry,
    report_sink,
)
from testbed.reporting.collector import PROJECT_KEY, ReportCollector
from testbed.reporting.json_sink import JsonSink
from testbed.retry import run_with_retries
from testbed.state import SINK_KEY


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addini(
        "testbed_project",
        "Default project adapter name for modules without a project marker.",
        default="",
    )
    parser.addini(
        "testbed_report_dir",
        "Directory for testbed reports and artifacts, relative to the rootdir.",
        default="reports",
    )
    parser.addoption(
        "--testbed-retries",
        type=int,
        default=1,
        dest="testbed_retries",
        help="Re-run a failing test call up to N times; a pass on retry is "
        "reported as flaky (0 disables).",
    )


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "project(name): select the testbed project adapter; module level only "
        "(use pytestmark = pytest.mark.project(...)); markers on single tests or "
        "classes are not honored by the adapter fixture",
    )
    sink = JsonSink(report_dir(config))
    config.stash[SINK_KEY] = sink
    config.pluginmanager.register(
        ReportCollector(sink, is_worker=hasattr(config, "workerinput")),
        "testbed-collector",
    )


@pytest.hookimpl(wrapper=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    report = yield
    project = resolve_project_name(item, item.config)
    if project:
        report.user_properties.append((PROJECT_KEY, project))
    return report


def pytest_runtest_protocol(item: pytest.Item, nextitem: pytest.Item | None):
    retries = item.config.getoption("testbed_retries")
    if retries <= 0:
        return None
    return run_with_retries(item, nextitem, retries)
