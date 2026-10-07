from __future__ import annotations

import re
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

from testbed.config import EnvConfig, report_dir
from testbed.discovery import (
    AdapterFactory,
    create_adapter,
    load_registry,
    resolve_project_name,
)
from testbed.ports import ProjectAdapter, ReportSink
from testbed.state import SINK_KEY

__all__ = ["adapter", "artifact_dir", "aws_session", "client", "env_config", "registry", "report_sink"]


@pytest.fixture(scope="session")
def env_config() -> EnvConfig:
    return EnvConfig()


@pytest.fixture(scope="session")
def registry() -> dict[str, AdapterFactory]:
    return load_registry()


@pytest.fixture(scope="module")
def adapter(
    request: pytest.FixtureRequest,
    registry: dict[str, AdapterFactory],
    env_config: EnvConfig,
) -> Iterator[ProjectAdapter]:
    name = resolve_project_name(request.node, request.config)
    instance = create_adapter(registry, name, env_config)
    instance.setup()
    try:
        if not instance.health_check():
            pytest.fail(f"project {name!r} failed its health check", pytrace=False)
        yield instance
    finally:
        instance.teardown()


@pytest.fixture
def client(adapter: ProjectAdapter) -> Any:
    return adapter.client()


@pytest.fixture
def artifact_dir(request: pytest.FixtureRequest) -> Path:
    safe_name = re.sub(r"[^\w.-]+", "_", request.node.nodeid)
    path = report_dir(request.config) / "artifacts" / safe_name
    path.mkdir(parents=True, exist_ok=True)
    return path


@pytest.fixture(scope="session")
def aws_session(env_config: EnvConfig) -> Any:
    try:
        import boto3
    except ImportError:
        pytest.fail(
            "boto3 is required for the aws_session fixture; install testbed-core[aws]",
            pytrace=False,
        )
    return boto3.Session(region_name=env_config.get("AWS_REGION"))


@pytest.fixture(scope="session")
def report_sink(request: pytest.FixtureRequest) -> ReportSink:
    return request.config.stash[SINK_KEY]
