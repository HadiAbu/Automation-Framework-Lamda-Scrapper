from __future__ import annotations

from collections.abc import Iterator
from typing import Any

import pytest

from testbed.config import EnvConfig
from testbed.discovery import (
    AdapterFactory,
    create_adapter,
    load_registry,
    resolve_project_name,
)
from testbed.ports import ProjectAdapter

__all__ = ["adapter", "client", "env_config", "registry"]


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
