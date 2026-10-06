def test_adapter_and_client_resolve_from_project_marker(pytester):
    pytester.makepyfile(
        """
        import pytest

        pytestmark = pytest.mark.project("fake")

        def test_it(adapter, client):
            assert adapter.name == "fake"
            assert adapter.events == ["setup"]
            assert client.echo(3) == 3
        """
    )
    pytester.runpytest().assert_outcomes(passed=1)


def test_adapter_resolves_from_ini_default(pytester):
    pytester.makeini("[pytest]\ntestbed_project = fake\n")
    pytester.makepyfile("def test_it(adapter):\n    assert adapter.name == 'fake'\n")
    pytester.runpytest().assert_outcomes(passed=1)


def test_adapter_is_shared_within_a_module_and_torn_down_after(pytester):
    pytester.makeconftest(
        """
        import pytest
        from pathlib import Path
        from testbed.fakes import FakeAdapter

        class Tracked(FakeAdapter):
            name = "tracked"
            def teardown(self):
                Path("teardown.flag").write_text("x")

        @pytest.fixture(scope="session")
        def registry():
            return {"tracked": Tracked}
        """
    )
    pytester.makepyfile(
        """
        import pytest
        from pathlib import Path

        pytestmark = pytest.mark.project("tracked")
        seen = []

        def test_a(adapter):
            seen.append(id(adapter))

        def test_b(adapter):
            seen.append(id(adapter))
            assert seen[0] == seen[1]
            assert adapter.events == ["setup"]
            assert not Path("teardown.flag").exists()
        """
    )
    pytester.runpytest().assert_outcomes(passed=2)
    assert (pytester.path / "teardown.flag").exists()


def test_unknown_project_is_an_error_naming_the_project(pytester):
    pytester.makepyfile(
        """
        import pytest

        pytestmark = pytest.mark.project("nope")

        def test_it(adapter):
            pass
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*unknown project 'nope'*"])


def test_missing_project_selection_is_an_error(pytester):
    pytester.makepyfile("def test_it(adapter):\n    pass\n")
    result = pytester.runpytest()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*no project selected*"])


def test_failed_health_check_errors_but_still_tears_down(pytester):
    pytester.makeconftest(
        """
        import pytest
        from pathlib import Path
        from testbed.fakes import FakeAdapter

        class Sick(FakeAdapter):
            name = "sick"
            def health_check(self):
                return False
            def teardown(self):
                Path("teardown.flag").write_text("x")

        @pytest.fixture(scope="session")
        def registry():
            return {"sick": Sick}
        """
    )
    pytester.makepyfile(
        """
        import pytest

        pytestmark = pytest.mark.project("sick")

        def test_it(adapter):
            pass
        """
    )
    result = pytester.runpytest()
    result.assert_outcomes(errors=1)
    result.stdout.fnmatch_lines(["*health check*"])
    assert (pytester.path / "teardown.flag").exists()
