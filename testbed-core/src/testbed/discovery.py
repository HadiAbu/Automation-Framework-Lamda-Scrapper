from __future__ import annotations

from collections.abc import Callable
from importlib import metadata
from typing import Any

from testbed.errors import (
    DuplicateProjectError,
    ProjectNotSelectedError,
    UnknownProjectError,
)
from testbed.ports import Environment, ProjectAdapter

ENTRY_POINT_GROUP = "testbed.projects"

AdapterFactory = Callable[[Environment], ProjectAdapter]


def load_registry(entry_points: Callable[..., Any] | None = None) -> dict[str, AdapterFactory]:
    find = entry_points or metadata.entry_points
    registry: dict[str, AdapterFactory] = {}
    for ep in find(group=ENTRY_POINT_GROUP):
        if ep.name in registry:
            raise DuplicateProjectError(f"project {ep.name!r} is registered more than once")
        registry[ep.name] = ep.load()
    return registry


def resolve_project_name(node: Any, config: Any) -> str | None:
    marker = node.get_closest_marker("project")
    if marker is not None and marker.args:
        return marker.args[0]
    return config.getini("testbed_project") or None


def create_adapter(
    registry: dict[str, AdapterFactory], name: str | None, env: Environment
) -> ProjectAdapter:
    if name is None:
        raise ProjectNotSelectedError(
            "no project selected: add pytestmark = pytest.mark.project('<name>') "
            "or set testbed_project in the pytest ini file"
        )
    try:
        factory = registry[name]
    except KeyError:
        raise UnknownProjectError(
            f"unknown project {name!r}; registered projects: {sorted(registry)}"
        ) from None
    return factory(env)
