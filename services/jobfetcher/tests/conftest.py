from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def greenhouse_payload() -> bytes:
    return (FIXTURES / "greenhouse_jobs.json").read_bytes()


@pytest.fixture
def lever_payload() -> bytes:
    return (FIXTURES / "lever_postings.json").read_bytes()


@pytest.fixture
def fake_http():
    def make(responses):
        calls = []

        def get(url):
            calls.append(url)
            value = responses[url]
            if isinstance(value, Exception):
                raise value
            return value

        get.calls = calls
        return get

    return make
