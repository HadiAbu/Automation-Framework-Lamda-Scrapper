import pytest

from jobfetcher.sources.greenhouse import GreenhouseSource

FIGMA_URL = "https://boards-api.greenhouse.io/v1/boards/figma/jobs?content=true"


def test_label_combines_kind_and_board_name():
    assert GreenhouseSource("figma", None).label == "greenhouse:figma"


def test_fetch_normalizes_jobs(fake_http, greenhouse_payload):
    http = fake_http({FIGMA_URL: greenhouse_payload})
    first, second = GreenhouseSource("figma", http).fetch()

    assert http.calls == [FIGMA_URL]
    assert first.id == "5426468004"
    assert first.source == "greenhouse:figma"
    assert first.company == "Figma"
    assert first.title == "Account Executive, Enterprise"
    assert first.location == "San Francisco, CA"
    assert first.url == "https://boards.greenhouse.io/figma/jobs/5426468004"
    assert first.posted_at == "2025-01-28T18:57:29-05:00"
    assert first.description == "We use Python & automation."
    assert first.matched_keywords == []


def test_fetch_falls_back_when_optional_fields_are_missing(fake_http, greenhouse_payload):
    http = fake_http({FIGMA_URL: greenhouse_payload})
    _, second = GreenhouseSource("figma", http).fetch()

    assert second.company == "figma"
    assert second.location == ""
    assert second.posted_at == "2026-07-23T05:37:08-04:00"
    assert second.description == ""


def test_http_errors_propagate(fake_http):
    http = fake_http({FIGMA_URL: OSError("down")})
    with pytest.raises(OSError, match="down"):
        GreenhouseSource("figma", http).fetch()


def test_malformed_payload_raises(fake_http):
    http = fake_http({FIGMA_URL: b'{"nope": 1}'})
    with pytest.raises(KeyError):
        GreenhouseSource("figma", http).fetch()
