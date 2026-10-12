import urllib.request

from jobfetcher.http import urllib_get


class _Response:
    def __init__(self, body):
        self._body = body

    def read(self):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_urllib_get_sends_user_agent_and_timeout(monkeypatch):
    seen = {}

    def fake_urlopen(request, timeout):
        seen["agent"] = request.get_header("User-agent")
        seen["url"] = request.full_url
        seen["timeout"] = timeout
        return _Response(b"{}")

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    assert urllib_get("https://example.test/x", timeout=7) == b"{}"
    assert seen == {
        "agent": "testbed-jobfetcher/0.1",
        "url": "https://example.test/x",
        "timeout": 7,
    }
