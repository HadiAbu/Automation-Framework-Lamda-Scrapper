from importlib.metadata import EntryPoint
from types import SimpleNamespace

import pytest

from testbed.config import EnvConfig
from testbed.discovery import (
    ENTRY_POINT_GROUP,
    create_adapter,
    load_registry,
    resolve_project_name,
)
from testbed.errors import (
    DuplicateProjectError,
    ProjectNotSelectedError,
    UnknownProjectError,
)
from testbed.fakes import FakeAdapter


def _eps(*names):
    return lambda group: [
        EntryPoint(name, "testbed.fakes:FakeAdapter", group) for name in names
    ]


def test_load_registry_maps_entry_point_names_to_factories():
    assert load_registry(_eps("alpha", "beta")) == {
        "alpha": FakeAdapter,
        "beta": FakeAdapter,
    }


def test_load_registry_rejects_duplicate_names():
    with pytest.raises(DuplicateProjectError, match="alpha"):
        load_registry(_eps("alpha", "alpha"))


def test_load_registry_queries_the_projects_group():
    seen = []

    def fake_entry_points(group):
        seen.append(group)
        return []

    load_registry(fake_entry_points)
    assert seen == [ENTRY_POINT_GROUP]


def test_installed_entry_points_include_the_fake_project():
    assert load_registry()["fake"] is FakeAdapter


def test_create_adapter_builds_from_registry():
    adapter = create_adapter({"fake": FakeAdapter}, "fake", EnvConfig({}))
    assert isinstance(adapter, FakeAdapter)


def test_create_adapter_unknown_project_lists_registered_names():
    with pytest.raises(UnknownProjectError, match=r"unknown project 'nope'.*fake"):
        create_adapter({"fake": FakeAdapter}, "nope", EnvConfig({}))


def test_create_adapter_requires_a_name():
    with pytest.raises(ProjectNotSelectedError):
        create_adapter({"fake": FakeAdapter}, None, EnvConfig({}))


class _Node:
    def __init__(self, marker):
        self._marker = marker

    def get_closest_marker(self, name):
        assert name == "project"
        return self._marker


class _Config:
    def __init__(self, ini):
        self._ini = ini

    def getini(self, key):
        assert key == "testbed_project"
        return self._ini


def test_resolve_project_name_prefers_marker():
    marker = SimpleNamespace(args=("from-marker",))
    assert resolve_project_name(_Node(marker), _Config("from-ini")) == "from-marker"


def test_resolve_project_name_falls_back_to_ini():
    assert resolve_project_name(_Node(None), _Config("from-ini")) == "from-ini"


def test_resolve_project_name_none_when_unset():
    assert resolve_project_name(_Node(None), _Config("")) is None
