from datetime import datetime, timezone

from jobfetcher.config import load_config
from jobfetcher.models import JobPost
from jobfetcher.pipeline import build_sources, run_pipeline
from jobfetcher.sources.base import JobSource

NOW = datetime(2026, 10, 7, 5, 0, tzinfo=timezone.utc)


class StubSource(JobSource):
    kind = "stub"

    def __init__(self, name, jobs=None, error=None):
        super().__init__(name, http_get=None)
        self._jobs = jobs or []
        self._error = error

    def fetch(self):
        if self._error is not None:
            raise self._error
        return list(self._jobs)


def job(id="1", source="stub:a", title="Engineer", description=""):
    return JobPost(
        id=id,
        source=source,
        company="C",
        title=title,
        location="",
        url=f"https://e/{id}",
        posted_at=None,
        description=description,
    )


def test_document_shape_and_injected_clock():
    doc = run_pipeline([StubSource("a", [job()])], ("python",), NOW)
    assert doc["generated_at"] == "2026-10-07T05:00:00+00:00"
    assert doc["sources"] == [{"name": "stub:a", "ok": True, "count": 1, "error": None}]
    assert [j["id"] for j in doc["jobs"]] == ["1"]


def test_failing_source_is_isolated_and_reported():
    good = StubSource("good", [job(source="stub:good")])
    bad = StubSource("bad", error=OSError("connection refused"))
    doc = run_pipeline([bad, good], (), NOW)

    assert doc["sources"][0] == {
        "name": "stub:bad",
        "ok": False,
        "count": 0,
        "error": "OSError: connection refused",
    }
    assert doc["sources"][1]["ok"] is True
    assert len(doc["jobs"]) == 1


def test_long_error_messages_are_truncated_to_300_characters():
    bad = StubSource("bad", error=RuntimeError("x" * 1000))
    doc = run_pipeline([bad], (), NOW)
    assert len(doc["sources"][0]["error"]) == 300


def test_duplicates_within_a_source_collapse_but_the_same_id_across_sources_is_kept():
    a = StubSource("a", [job(id="1", source="stub:a"), job(id="1", source="stub:a")])
    b = StubSource("b", [job(id="1", source="stub:b")])
    doc = run_pipeline([a, b], (), NOW)
    assert [(j["source"], j["id"]) for j in doc["jobs"]] == [("stub:a", "1"), ("stub:b", "1")]


def test_keywords_match_whole_words_in_title_and_description():
    source = StubSource(
        "a",
        [
            job(id="1", title="SDET", description="We write Python."),
            job(id="2", title="Engineer", description="Latest news, testing things"),
        ],
    )
    doc = run_pipeline([source], ("python", "sdet", "test", "testing"), NOW)
    assert doc["jobs"][0]["matched_keywords"] == ["python", "sdet"]
    assert doc["jobs"][1]["matched_keywords"] == ["testing"]


def test_build_sources_maps_the_default_config_to_five_strategies():
    sources = build_sources(load_config(), http_get=None)
    assert [s.label for s in sources] == [
        "greenhouse:stripe",
        "greenhouse:figma",
        "greenhouse:cloudflare",
        "lever:spotify",
        "lever:palantir",
    ]
