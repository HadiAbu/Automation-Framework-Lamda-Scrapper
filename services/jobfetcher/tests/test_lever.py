import pytest

from jobfetcher.config import BOARD_TYPES, BoardConfig
from jobfetcher.sources import SOURCE_TYPES, create_source
from jobfetcher.sources.greenhouse import GreenhouseSource
from jobfetcher.sources.lever import LeverSource

SPOTIFY_URL = "https://api.lever.co/v0/postings/spotify?mode=json"


def test_label_combines_kind_and_board_name():
    assert LeverSource("spotify", None).label == "lever:spotify"


def test_fetch_normalizes_postings(fake_http, lever_payload):
    http = fake_http({SPOTIFY_URL: lever_payload})
    first, second = LeverSource("spotify", http).fetch()

    assert http.calls == [SPOTIFY_URL]
    assert first.id == "2193db3f-77c5-43b8-b030-8f92c9882bf1"
    assert first.source == "lever:spotify"
    assert first.company == "Spotify"
    assert first.title == "Android Engineer - Experience"
    assert first.location == "Stockholm"
    assert first.url == "https://jobs.lever.co/spotify/2193db3f-77c5-43b8-b030-8f92c9882bf1"
    assert first.posted_at.startswith("2026-")
    assert first.description == "Build Python tools."


def test_fetch_handles_missing_optional_fields(fake_http, lever_payload):
    http = fake_http({SPOTIFY_URL: lever_payload})
    _, second = LeverSource("spotify", http).fetch()

    assert second.title == "QA Lead"
    assert second.location == ""
    assert second.description == ""
    assert second.posted_at == "2023-11-14T22:13:20+00:00"


def test_http_errors_propagate(fake_http):
    http = fake_http({SPOTIFY_URL: OSError("down")})
    with pytest.raises(OSError, match="down"):
        LeverSource("spotify", http).fetch()


def test_registry_covers_every_configured_board_type():
    assert set(SOURCE_TYPES) == set(BOARD_TYPES)


def test_create_source_builds_the_right_strategy():
    greenhouse = create_source(BoardConfig("greenhouse", "stripe"), None)
    lever = create_source(BoardConfig("lever", "spotify"), None)
    assert isinstance(greenhouse, GreenhouseSource) and greenhouse.name == "stripe"
    assert isinstance(lever, LeverSource) and lever.name == "spotify"


def test_display_name_titlecases_slug():
    assert LeverSource("palantir", None).display_name == "Palantir"
    assert LeverSource("my-company_x", None).display_name == "My Company X"
