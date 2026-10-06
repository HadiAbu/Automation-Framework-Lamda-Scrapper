import sys
import types
from pathlib import Path
from types import SimpleNamespace

from testbed.config import report_dir


def test_report_dir_is_relative_to_rootpath():
    config = SimpleNamespace(rootpath=Path("/root"), getini=lambda key: "out")
    assert report_dir(config) == Path("/root/out")


def test_report_dir_honours_absolute_ini_value(tmp_path):
    config = SimpleNamespace(rootpath=Path("/root"), getini=lambda key: str(tmp_path))
    assert report_dir(config) == tmp_path


def test_env_config_fixture_reads_process_environment(pytester, monkeypatch):
    monkeypatch.setenv("TESTBED_PROBE", "bar")
    pytester.makepyfile(
        """
        def test_it(env_config):
            assert env_config.require("TESTBED_PROBE") == "bar"
        """
    )
    pytester.runpytest().assert_outcomes(passed=1)


def test_artifact_dir_is_unique_per_test_and_under_report_dir(pytester):
    pytester.makepyfile(
        """
        _seen = []

        def test_a(artifact_dir):
            (artifact_dir / "a.txt").write_text("a")
            assert artifact_dir.parent.name == "artifacts"
            assert artifact_dir.parent.parent.name == "reports"
            _seen.append(artifact_dir)

        def test_b(artifact_dir):
            assert artifact_dir.is_dir()
            assert artifact_dir not in _seen
        """
    )
    pytester.runpytest().assert_outcomes(passed=2)
    assert list((pytester.path / "reports" / "artifacts").glob("*/a.txt"))


def test_aws_session_uses_region_from_environment(pytester, monkeypatch):
    fake = types.SimpleNamespace(Session=lambda region_name=None: ("session", region_name))
    monkeypatch.setitem(sys.modules, "boto3", fake)
    monkeypatch.setenv("AWS_REGION", "eu-west-1")
    pytester.makepyfile(
        """
        def test_it(aws_session):
            assert aws_session == ("session", "eu-west-1")
        """
    )
    pytester.runpytest().assert_outcomes(passed=1)


def test_aws_session_fails_loudly_without_boto3(pytester, monkeypatch):
    monkeypatch.setitem(sys.modules, "boto3", None)
    pytester.makepyfile("def test_it(aws_session):\n    pass\n")
    result = pytester.runpytest()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*testbed-core[[]aws[]]*"])
