import json
from importlib import metadata


def test_plugin_and_fake_project_are_registered_via_entry_points():
    pytest11 = {ep.name for ep in metadata.entry_points(group="pytest11")}
    projects = {ep.name for ep in metadata.entry_points(group="testbed.projects")}
    assert "testbed" in pytest11
    assert "fake" in projects


def test_a_project_suite_runs_end_to_end_and_reports(pytester):
    pytester.makepyfile(
        counter="""
        from pathlib import Path

        def bump():
            marker = Path("attempts.txt")
            n = int(marker.read_text()) if marker.exists() else 0
            marker.write_text(str(n + 1))
            return n
        """,
        test_fake_project="""
        import pytest
        from counter import bump

        pytestmark = pytest.mark.project("fake")

        def test_stable(client):
            assert client.echo("hi") == "hi"

        def test_flaky(adapter):
            assert bump() >= 1

        def test_writes_artifact(artifact_dir):
            (artifact_dir / "out.txt").write_text("ok")

        @pytest.mark.skip(reason="demo skip")
        def test_skipped():
            pass
        """,
    )
    result = pytester.runpytest()
    result.assert_outcomes(passed=3, skipped=1)
    result.stdout.fnmatch_lines(["*testbed report:*"])

    data = json.loads((pytester.path / "reports" / "report.json").read_text())
    assert data["summary"] == {"total": 4, "passed": 2, "failed": 0, "skipped": 1, "flaky": 1}
    assert {r["project"] for r in data["results"]} == {"fake"}
    assert list((pytester.path / "reports" / "artifacts").glob("*/out.txt"))
