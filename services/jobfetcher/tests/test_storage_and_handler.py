import json
from datetime import datetime, timezone

import pytest

from jobfetcher.config import load_config
from jobfetcher.handler import AllSourcesFailedError, lambda_handler
from jobfetcher.sources.greenhouse import GreenhouseSource
from jobfetcher.sources.lever import LeverSource
from jobfetcher.storage import S3Store

NOW = datetime(2026, 10, 7, 5, 0, tzinfo=timezone.utc)


def test_store_writes_dated_and_latest_objects(fake_s3):
    document = {"jobs": [], "sources": []}
    keys = S3Store("bkt", fake_s3).write(document, "2026-10-07")

    assert keys == ["jobs/2026-10-07.json", "jobs/latest.json"]
    assert [p["Key"] for p in fake_s3.puts] == keys
    assert {p["Bucket"] for p in fake_s3.puts} == {"bkt"}
    assert all(p["ContentType"] == "application/json" for p in fake_s3.puts)
    assert json.loads(fake_s3.puts[0]["Body"]) == document
    assert fake_s3.puts[0]["Body"] == fake_s3.puts[1]["Body"]


def _responses(greenhouse_payload, lever_payload):
    responses = {}
    for board in load_config().boards:
        if board.type == "greenhouse":
            responses[GreenhouseSource.URL.format(name=board.name)] = greenhouse_payload
        else:
            responses[LeverSource.URL.format(name=board.name)] = lever_payload
    return responses


def test_run_writes_both_objects_and_returns_a_summary(
    monkeypatch, fake_http, fake_s3, greenhouse_payload, lever_payload
):
    monkeypatch.setenv("BUCKET_NAME", "bkt")
    http = fake_http(_responses(greenhouse_payload, lever_payload))

    result = lambda_handler({}, None, http_get=http, s3_client=fake_s3, now=NOW)

    assert result["dry_run"] is False
    assert result["keys"] == ["jobs/2026-10-07.json", "jobs/latest.json"]
    assert result["job_count"] == 10  # 3 greenhouse boards x 2 + 2 lever boards x 2
    assert all(s["ok"] for s in result["sources"])
    written = json.loads(fake_s3.puts[1]["Body"])
    assert len(written["jobs"]) == 10
    assert written["generated_at"] == "2026-10-07T05:00:00+00:00"


def test_dry_run_skips_s3_and_does_not_need_a_bucket(
    monkeypatch, fake_http, fake_s3, greenhouse_payload, lever_payload
):
    monkeypatch.delenv("BUCKET_NAME", raising=False)
    http = fake_http(_responses(greenhouse_payload, lever_payload))

    result = lambda_handler({"dry_run": True}, None, http_get=http, s3_client=fake_s3, now=NOW)

    assert result["dry_run"] is True
    assert "keys" not in result
    assert result["job_count"] == 10
    assert fake_s3.puts == []


def test_one_failing_source_is_reported_but_the_run_still_writes(
    monkeypatch, fake_http, fake_s3, greenhouse_payload, lever_payload
):
    monkeypatch.setenv("BUCKET_NAME", "bkt")
    responses = _responses(greenhouse_payload, lever_payload)
    responses[GreenhouseSource.URL.format(name="stripe")] = OSError("down")
    http = fake_http(responses)

    result = lambda_handler({}, None, http_get=http, s3_client=fake_s3, now=NOW)

    failed = [s for s in result["sources"] if not s["ok"]]
    assert [s["name"] for s in failed] == ["greenhouse:stripe"]
    assert result["job_count"] == 8
    assert len(fake_s3.puts) == 2


def test_all_sources_failing_raises_and_writes_nothing(
    monkeypatch, fake_http, fake_s3, greenhouse_payload, lever_payload
):
    monkeypatch.setenv("BUCKET_NAME", "bkt")
    responses = {url: OSError("down") for url in _responses(greenhouse_payload, lever_payload)}
    http = fake_http(responses)

    with pytest.raises(AllSourcesFailedError, match="all 5 sources failed"):
        lambda_handler({}, None, http_get=http, s3_client=fake_s3, now=NOW)
    assert fake_s3.puts == []


def test_missing_bucket_name_is_an_error_outside_dry_run(
    monkeypatch, fake_http, fake_s3, greenhouse_payload, lever_payload
):
    monkeypatch.delenv("BUCKET_NAME", raising=False)
    http = fake_http(_responses(greenhouse_payload, lever_payload))

    with pytest.raises(KeyError, match="BUCKET_NAME"):
        lambda_handler({}, None, http_get=http, s3_client=fake_s3, now=NOW)
