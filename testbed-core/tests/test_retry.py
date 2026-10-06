import json

COUNTER = """
from pathlib import Path

def bump():
    marker = Path("attempts.txt")
    n = int(marker.read_text()) if marker.exists() else 0
    marker.write_text(str(n + 1))
    return n
"""


def _data(pytester):
    return json.loads((pytester.path / "reports" / "report.json").read_text())


def _attempts(pytester):
    return int((pytester.path / "attempts.txt").read_text())


def test_pass_on_retry_is_reported_as_flaky_not_passed(pytester):
    pytester.makepyfile(
        counter=COUNTER,
        test_flaky="""
        from counter import bump

        def test_flaky():
            assert bump() >= 1, "first attempt fails"
        """,
    )
    pytester.runpytest().assert_outcomes(passed=1)
    data = _data(pytester)
    assert data["summary"]["flaky"] == 1
    assert data["summary"]["passed"] == 0
    assert "first attempt fails" in data["results"][0]["message"]
    assert _attempts(pytester) == 2


def test_consistently_failing_test_is_failed_after_one_retry(pytester):
    pytester.makepyfile(
        counter=COUNTER,
        test_bad="""
        from counter import bump

        def test_bad():
            bump()
            assert False
        """,
    )
    pytester.runpytest().assert_outcomes(failed=1)
    assert _data(pytester)["summary"]["failed"] == 1
    assert _attempts(pytester) == 2


def test_retries_option_zero_disables_retrying(pytester):
    pytester.makepyfile(
        counter=COUNTER,
        test_bad="""
        from counter import bump

        def test_bad():
            bump()
            assert False
        """,
    )
    pytester.runpytest("--testbed-retries=0").assert_outcomes(failed=1)
    assert _attempts(pytester) == 1


def test_retries_option_allows_more_than_one_retry(pytester):
    pytester.makepyfile(
        counter=COUNTER,
        test_flaky="""
        from counter import bump

        def test_flaky():
            assert bump() >= 2
        """,
    )
    pytester.runpytest("--testbed-retries=2").assert_outcomes(passed=1)
    assert _data(pytester)["summary"]["flaky"] == 1
    assert _attempts(pytester) == 3


def test_setup_errors_are_not_retried(pytester):
    pytester.makepyfile(
        counter=COUNTER,
        test_err="""
        import pytest
        from counter import bump

        @pytest.fixture
        def broken():
            bump()
            raise RuntimeError("setup failed")

        def test_err(broken):
            pass
        """,
    )
    pytester.runpytest().assert_outcomes(errors=1)
    assert _attempts(pytester) == 1


def test_stable_tests_are_unaffected_by_retry(pytester):
    pytester.makepyfile("def test_ok():\n    pass\n")
    pytester.runpytest().assert_outcomes(passed=1)
    assert _data(pytester)["summary"]["flaky"] == 0
