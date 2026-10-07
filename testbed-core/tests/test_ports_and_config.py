import pytest

from testbed.config import EnvConfig
from testbed.errors import MissingConfigError
from testbed.ports import Environment, ProjectAdapter, ReportSink


def test_env_config_get_returns_value_or_default():
    env = EnvConfig({"A": "1"})
    assert env.get("A") == "1"
    assert env.get("B") is None
    assert env.get("B", "fallback") == "fallback"


def test_env_config_require_returns_value():
    assert EnvConfig({"A": "1"}).require("A") == "1"


def test_env_config_require_raises_for_missing_or_empty():
    with pytest.raises(MissingConfigError, match="'A'"):
        EnvConfig({}).require("A")
    with pytest.raises(MissingConfigError, match="'A'"):
        EnvConfig({"A": ""}).require("A")


def test_env_config_defaults_to_live_process_environment(monkeypatch):
    monkeypatch.setenv("TESTBED_PROBE", "yes")
    assert EnvConfig().require("TESTBED_PROBE") == "yes"


def test_env_config_satisfies_environment_port():
    assert isinstance(EnvConfig({}), Environment)


def test_ports_are_abstract():
    with pytest.raises(TypeError):
        ProjectAdapter()
    with pytest.raises(TypeError):
        ReportSink()


def test_describe_defaults_to_name():
    class Dummy(ProjectAdapter):
        name = "dummy"

        def setup(self):
            pass

        def health_check(self):
            return True

        def client(self):
            return object()

        def teardown(self):
            pass

    assert Dummy().describe() == {"name": "dummy"}
