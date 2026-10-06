from __future__ import annotations

import pytest

from testbed.fixtures import adapter, client, env_config, registry  # noqa: F401


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


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers", "project(name): select the testbed project adapter for a test module"
    )
