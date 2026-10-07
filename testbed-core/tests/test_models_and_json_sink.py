import json
from datetime import datetime, timezone

from testbed.ports import ReportSink
from testbed.reporting.json_sink import JsonSink
from testbed.reporting.models import CaseResult, RunReport


def _report():
    return RunReport(
        started_at=datetime(2026, 10, 6, 12, 0, tzinfo=timezone.utc),
        duration=1.23456,
        results=[
            CaseResult("t.py::a", "fake", "passed", 0.1),
            CaseResult("t.py::b", "fake", "failed", 0.2, "boom"),
            CaseResult("t.py::c", None, "skipped", 0.0, "nope"),
            CaseResult("t.py::d", "fake", "flaky", 0.3, "first try failed"),
        ],
    )


def test_summary_counts_every_outcome():
    assert _report().summary() == {
        "total": 4,
        "passed": 1,
        "failed": 1,
        "skipped": 1,
        "flaky": 1,
    }


def test_ok_is_false_when_anything_failed_and_true_for_flaky_only():
    assert _report().ok is False
    flaky_only = RunReport(
        started_at=datetime.now(timezone.utc),
        duration=0,
        results=[CaseResult("t.py::d", None, "flaky", 0.1)],
    )
    assert flaky_only.ok is True


def test_to_dict_is_json_serialisable_and_rounds_duration():
    data = _report().to_dict()
    assert data["started_at"] == "2026-10-06T12:00:00+00:00"
    assert data["duration"] == 1.235
    assert data["results"][1] == {
        "nodeid": "t.py::b",
        "project": "fake",
        "outcome": "failed",
        "duration": 0.2,
        "message": "boom",
    }
    json.dumps(data)


def test_json_sink_is_a_report_sink():
    assert issubclass(JsonSink, ReportSink)


def test_json_sink_writes_report_and_returns_its_path(tmp_path):
    target = tmp_path / "nested" / "out"
    location = JsonSink(target).publish(_report())
    assert location == str(target / "report.json")
    assert json.loads((target / "report.json").read_text())["summary"]["total"] == 4
