import json

import pytest

from testbed.reporting.collector import (
    FIRST_FAILURE_KEY,
    FLAKY_KEY,
    PROJECT_KEY,
    ReportCollector,
)
from testbed.reporting.models import RunReport


class _Sink:
    def __init__(self):
        self.published = []

    def publish(self, report):
        self.published.append(report)
        return "memory://report"


def _report(when="call", outcome="passed", longrepr=None, props=(), duration=0.5):
    return pytest.TestReport(
        nodeid="t.py::test_x",
        location=("t.py", 1, "test_x"),
        keywords={},
        outcome=outcome,
        longrepr=longrepr,
        when=when,
        user_properties=list(props),
        duration=duration,
    )


def _single_result(report):
    collector = ReportCollector(_Sink())
    collector.pytest_runtest_logreport(report)
    results = collector.build().results
    assert len(results) == 1
    return results[0]


def test_passed_call_is_recorded_with_project_and_duration():
    result = _single_result(_report(props=[(PROJECT_KEY, "fake")]))
    assert (result.outcome, result.project, result.duration) == ("passed", "fake", 0.5)
    assert result.message is None


def test_failed_call_records_the_failure_text():
    result = _single_result(_report(outcome="failed", longrepr="assert 1 == 2"))
    assert result.outcome == "failed"
    assert "assert 1 == 2" in result.message


def test_long_failure_text_is_truncated():
    result = _single_result(_report(outcome="failed", longrepr="x" * 5000))
    assert len(result.message) == 2000


def test_setup_failure_counts_as_failed_and_setup_pass_is_ignored():
    assert _single_result(_report(when="setup", outcome="failed", longrepr="boom")).outcome == "failed"
    collector = ReportCollector(_Sink())
    collector.pytest_runtest_logreport(_report(when="setup", outcome="passed"))
    collector.pytest_runtest_logreport(_report(when="teardown", outcome="passed"))
    assert collector.build().results == []


def test_teardown_failure_is_recorded_as_its_own_failed_entry():
    result = _single_result(_report(when="teardown", outcome="failed", longrepr="cleanup broke"))
    assert result.outcome == "failed"
    assert result.nodeid == "t.py::test_x [teardown]"
    assert "cleanup broke" in result.message


def test_skip_reason_is_recorded():
    result = _single_result(
        _report(when="setup", outcome="skipped", longrepr=("t.py", 3, "Skipped: not today"))
    )
    assert result.outcome == "skipped"
    assert "not today" in result.message


def test_pass_with_flaky_tag_becomes_flaky_with_first_failure_message():
    result = _single_result(
        _report(props=[(FLAKY_KEY, "1"), (FIRST_FAILURE_KEY, "first try failed")])
    )
    assert result.outcome == "flaky"
    assert result.message == "first try failed"


def test_sessionfinish_publishes_once_and_exposes_location():
    sink = _Sink()
    collector = ReportCollector(sink)
    collector.pytest_runtest_logreport(_report())
    collector.pytest_sessionfinish(session=None)
    assert isinstance(sink.published[0], RunReport)
    assert collector.location == "memory://report"


def test_worker_processes_do_not_publish():
    sink = _Sink()
    collector = ReportCollector(sink, is_worker=True)
    collector.pytest_sessionfinish(session=None)
    assert sink.published == []


def test_plugin_writes_report_json_with_projects_and_outcomes(pytester):
    pytester.makepyfile(
        """
        import pytest

        pytestmark = pytest.mark.project("fake")

        def test_pass(adapter):
            pass

        def test_fail():
            assert False, "kaboom"

        @pytest.mark.skip(reason="nope")
        def test_skip():
            pass
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(passed=1, failed=1, skipped=1)
    data = json.loads((pytester.path / "reports" / "report.json").read_text())
    assert data["summary"] == {"total": 3, "passed": 1, "failed": 1, "skipped": 1, "flaky": 0}
    assert {r["project"] for r in data["results"]} == {"fake"}
    failed = next(r for r in data["results"] if r["outcome"] == "failed")
    assert "kaboom" in failed["message"]


def test_results_without_a_project_have_none(pytester):
    pytester.makepyfile("def test_pass():\n    pass\n")
    pytester.runpytest().assert_outcomes(passed=1)
    data = json.loads((pytester.path / "reports" / "report.json").read_text())
    assert data["results"][0]["project"] is None


def test_report_location_is_printed_in_terminal_summary(pytester):
    pytester.makepyfile("def test_pass():\n    pass\n")
    result = pytester.runpytest()
    result.stdout.fnmatch_lines(["*testbed report:*report.json*"])


def test_report_dir_ini_option_is_respected(pytester):
    pytester.makeini("[pytest]\ntestbed_report_dir = out\n")
    pytester.makepyfile("def test_pass():\n    pass\n")
    pytester.runpytest().assert_outcomes(passed=1)
    assert (pytester.path / "out" / "report.json").exists()


def test_report_sink_fixture_is_the_session_sink(pytester):
    pytester.makepyfile(
        """
        from testbed.ports import ReportSink

        def test_it(report_sink):
            assert isinstance(report_sink, ReportSink)
        """
    )
    pytester.runpytest().assert_outcomes(passed=1)
