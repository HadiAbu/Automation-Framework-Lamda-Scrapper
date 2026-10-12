from jobfetcher.models import JobPost, SourceResult
from jobfetcher.text import html_to_text


def _post(**overrides):
    base = dict(
        id="1",
        source="greenhouse:x",
        company="X",
        title="T",
        location="L",
        url="https://e/1",
        posted_at=None,
        description="d",
    )
    base.update(overrides)
    return JobPost(**base)


def test_job_post_to_dict_has_the_documented_keys_in_order():
    assert list(_post().to_dict()) == [
        "id",
        "source",
        "company",
        "title",
        "location",
        "url",
        "posted_at",
        "description",
        "matched_keywords",
    ]


def test_matched_keywords_defaults_to_a_fresh_empty_list_per_instance():
    a, b = _post(), _post()
    assert a.matched_keywords == []
    assert a.matched_keywords is not b.matched_keywords


def test_source_result_status_reports_count_and_error():
    ok = SourceResult("lever:x", ok=True, jobs=[_post(), _post(id="2")])
    assert ok.status() == {"name": "lever:x", "ok": True, "count": 2, "error": None}
    bad = SourceResult("lever:y", ok=False, error="boom")
    assert bad.status() == {"name": "lever:y", "ok": False, "count": 0, "error": "boom"}


def test_html_to_text_decodes_entity_escaped_html():
    raw = "&lt;p&gt;Hello &amp;amp; welcome&lt;/p&gt;"
    assert html_to_text(raw) == "Hello & welcome"


def test_html_to_text_strips_plain_html_tags():
    assert html_to_text("<div>a</div><div>b</div>") == "a b"


def test_html_to_text_collapses_whitespace():
    assert html_to_text("a\n\n   b\t c") == "a b c"


def test_html_to_text_empty_string():
    assert html_to_text("") == ""
