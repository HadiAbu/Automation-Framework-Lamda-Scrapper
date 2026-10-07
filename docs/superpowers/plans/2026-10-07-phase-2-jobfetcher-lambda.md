# testbed Phase 2 (Job-Fetcher Lambda + SAM) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. **Task 8 is MANUAL**: it needs the user's AWS account and credentials, so the controller guides the user through it; no subagent runs it and the assistant never sees credentials.

**Goal:** Build and deploy `services/jobfetcher/`, an AWS Lambda that fetches job posts from public Greenhouse and Lever board APIs on a daily schedule, normalizes and keyword-tags them, and writes `jobs/<date>.json` and `jobs/latest.json` to S3, defined with AWS SAM and deployed to `eu-north-1`.

**Architecture:** One Lambda loops over the configured boards sequentially. Each source (a `JobSource` strategy) runs inside its own `try/except`, so one failing board is recorded in the output and does not fail the run; the run fails only if every source failed. The HTTP fetcher and the S3 client are injected, so all logic is tested offline against fixtures shaped like the real APIs. A `dry_run` event flag runs the whole pipeline without touching S3.

**Tech Stack:** Python 3.13 (stdlib `urllib`, `dataclasses`; Lambda-provided `boto3`), pytest, PyYAML (test-only), AWS SAM CLI, AWS CLI v2, Docker (for `sam local invoke`).

**Spec:** `docs/superpowers/specs/2026-10-06-testbed-design.md`, section "Phase 2 detail" (Task 1 corrects five numbers in it first).

## Global Constraints

- Python `>=3.13`. Lambda: runtime `python3.13`, architecture **`x86_64`** (see Ruling A), memory **512 MB**, timeout **120 s**.
- No third-party **runtime** dependencies: stdlib `urllib` for HTTP; `boto3` comes from the Lambda runtime and is imported lazily so tests run without it. No Lambda layer; no `requirements.txt` in `src/`.
- Code lives in `services/jobfetcher/`; the importable package is `jobfetcher` under `services/jobfetcher/src/`. Its tests run from the repo root with `.venv/Scripts/python -m pytest services/jobfetcher/tests` and disable the testbed plugin (`-p no:testbed`).
- Sources (public, unauthenticated): Greenhouse `https://boards-api.greenhouse.io/v1/boards/{name}/jobs?content=true`; Lever `https://api.lever.co/v0/postings/{name}?mode=json`. Default boards: Greenhouse `stripe`, `figma`, `cloudflare`; Lever `spotify`, `palantir`. Board list and keywords live in `src/jobfetcher/boards.json`, never in code.
- Output document: `{"generated_at": ISO-8601, "sources": [{"name","ok","count","error"}], "jobs": [{"id","source","company","title","location","url","posted_at","description","matched_keywords"}]}`, written to `jobs/<YYYY-MM-DD>.json` and `jobs/latest.json` (UTC date). Jobs are deduplicated by `(source, id)`; all jobs are kept.
- Per-source error text is `"<ExceptionType>: <message>"` truncated to 300 characters.
- AWS: region `eu-north-1`, stack name `testbed-jobfetcher`, bucket with SSE on and all four public-access blocks on, lifecycle expiry of 30 days on prefix `jobs/20` (dated objects only, never `latest.json`), Lambda role limited to `s3:PutObject` on `<bucket>/jobs/*` plus the default logging policy. The GitHub OIDC role is deferred to Phase 4.
- Credentials are configured by the user locally (`aws configure`); they never appear in the repo, the chat, or any command the assistant runs. Resources are free-tier sized; `sam delete` removes them.
- Develop on branch `phase-2-lambda`; merge with `--no-ff`; never delete the branch. Never push without explicit per-instance user approval.
- Lean verification: run the targeted test file after each step and the full `services/jobfetcher/tests` suite at the end of each task.
- All commands run from the repo root in Git Bash; `PY` means `.venv/Scripts/python`.
- Commit messages end with the trailer `Co-Authored-By: Claude Sonnet 5.5 <noreply@anthropic.com>`.

## Rulings made while planning

- **Ruling A:** architecture `x86_64`, not `arm64` — `sam local invoke` would otherwise run an emulated arm64 image on this Windows x86 machine; arm64 is ~20% cheaper and a one-line change later. Memory 512 MB / timeout 120 s instead of the spec's 256 MB / 60 s — measured on 2026-10-07: the five boards return ~21 MB of JSON and take ~18 s sequentially.
- **Ruling B:** `boards.json` lives at `src/jobfetcher/boards.json` (not `config/boards.json`) so it ships inside the Lambda zip.
- **Ruling C:** the deploy identity is a dedicated non-root IAM user for this sandbox, not a least-privilege one; the Lambda's *runtime* role is least-privilege. Narrowing the deployer is a Phase 4 item (OIDC role).
- **Ruling D:** a `{"dry_run": true}` event runs fetch + normalize + tag and returns the summary without S3 or `BUCKET_NAME`, so `sam local invoke` needs no AWS credentials.

## File Structure

```
.gitignore                                   # + .aws-sam/
services/jobfetcher/
  pyproject.toml                             # pytest config only (pythonpath, -p no:testbed)
  requirements-dev.txt                       # pytest, pyyaml (test-only)
  template.yaml                              # SAM: bucket, function, schedule, IAM
  samconfig.toml                             # stack/region/deploy defaults
  events/dry-run.json                        # {"dry_run": true}
  src/jobfetcher/
    __init__.py
    boards.json                              # boards + keywords
    models.py                                # JobPost, SourceResult
    text.py                                  # html_to_text
    config.py                                # BoardConfig, Config, load_config
    http.py                                  # HttpGet, urllib_get
    pipeline.py                              # build_sources, fetch_source, tag_keywords, run_pipeline
    storage.py                               # S3Store
    handler.py                               # lambda_handler, AllSourcesFailedError
    sources/
      __init__.py                            # SOURCE_TYPES, create_source
      base.py                                # JobSource ABC
      greenhouse.py                          # GreenhouseSource
      lever.py                               # LeverSource
  tests/
    conftest.py                              # fixtures: payloads, fake_http, fake_s3
    fixtures/greenhouse_jobs.json
    fixtures/lever_postings.json
    test_models_and_text.py
    test_config.py
    test_http.py
    test_greenhouse.py
    test_lever.py
    test_pipeline.py
    test_storage_and_handler.py
    test_template.py
```

---

### Task 1: Scaffold, models, text helper, spec corrections

**Files:**
- Create: `services/jobfetcher/pyproject.toml`, `services/jobfetcher/requirements-dev.txt`, `services/jobfetcher/src/jobfetcher/__init__.py`, `services/jobfetcher/src/jobfetcher/models.py`, `services/jobfetcher/src/jobfetcher/text.py`
- Test: `services/jobfetcher/tests/test_models_and_text.py`
- Modify: `docs/superpowers/specs/2026-10-06-testbed-design.md` (Phase 2 detail section)

**Interfaces:**
- Produces: `jobfetcher.models.JobPost` (frozen dataclass; fields `id, source, company, title, location, url, posted_at: str | None, description, matched_keywords: list[str] = []`; `to_dict() -> dict`); `jobfetcher.models.SourceResult(name: str, ok: bool, jobs: list[JobPost] = [], error: str | None = None)` with `status() -> {"name","ok","count","error"}`; `jobfetcher.text.html_to_text(raw: str) -> str`.

- [ ] **Step 1: Create the branch check and scaffold files**

Run: `git branch --show-current` — expected `phase-2-lambda`.

`services/jobfetcher/pyproject.toml`:
```toml
[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
addopts = "-p no:testbed"
```

`services/jobfetcher/requirements-dev.txt`:
```
pytest>=8
pyyaml>=6
```

`services/jobfetcher/src/jobfetcher/__init__.py`: empty file.

Run: `.venv/Scripts/python -m pip install -r services/jobfetcher/requirements-dev.txt`
Expected: pyyaml installed (pytest already present).

- [ ] **Step 2: Write the failing tests**

`services/jobfetcher/tests/test_models_and_text.py`:
```python
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
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/Scripts/python -m pytest services/jobfetcher/tests/test_models_and_text.py -v`
Expected: collection ERROR `ModuleNotFoundError: No module named 'jobfetcher.models'`.

- [ ] **Step 4: Implement**

`services/jobfetcher/src/jobfetcher/models.py`:
```python
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class JobPost:
    id: str
    source: str
    company: str
    title: str
    location: str
    url: str
    posted_at: str | None
    description: str
    matched_keywords: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class SourceResult:
    name: str
    ok: bool
    jobs: list[JobPost] = field(default_factory=list)
    error: str | None = None

    def status(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "ok": self.ok,
            "count": len(self.jobs),
            "error": self.error,
        }
```

`services/jobfetcher/src/jobfetcher/text.py`:
```python
from __future__ import annotations

import html
import re

_TAG = re.compile(r"<[^>]+>")
_SPACE = re.compile(r"\s+")


def html_to_text(raw: str) -> str:
    """Greenhouse sends entity-escaped HTML: unescape, drop tags, unescape again."""
    text = html.unescape(raw)
    text = _TAG.sub(" ", text)
    text = html.unescape(text)
    return _SPACE.sub(" ", text).strip()
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv/Scripts/python -m pytest services/jobfetcher/tests -v`
Expected: 7 passed, no warnings, and no `reports/` or `.reports/` directory created under `services/jobfetcher/`.

- [ ] **Step 6: Correct the spec's Phase 2 detail section**

In `docs/superpowers/specs/2026-10-06-testbed-design.md`, "Phase 2 detail" section:
1. Layout line: replace `config/boards.json` with `src/jobfetcher/boards.json (ships inside the Lambda zip)`.
2. SAM template line: replace `Python 3.13, arm64, 256 MB, 60 s timeout` with `Python 3.13, x86_64, 512 MB, 120 s timeout (five boards return ~21 MB of JSON and take ~18 s sequentially, measured 2026-10-07)`.
3. AWS setup line: replace `deploy with a dedicated least-privilege identity rather than root` with `deploy with a dedicated non-root IAM user (the Lambda's runtime role is least-privilege; narrowing the deployer is a Phase 4 item)`.
4. Add to the Testing paragraph: `A {"dry_run": true} event runs fetch + normalize + tag and returns the summary without touching S3, so sam local invoke needs no AWS credentials.`

- [ ] **Step 7: Commit**

```bash
git add services docs
git commit -m "feat(jobfetcher): scaffold service with models and html_to_text; correct Phase 2 spec"
```

---

### Task 2: Board configuration

**Files:**
- Create: `services/jobfetcher/src/jobfetcher/boards.json`, `services/jobfetcher/src/jobfetcher/config.py`
- Test: `services/jobfetcher/tests/test_config.py`

**Interfaces:**
- Produces: `jobfetcher.config.BOARD_TYPES = ("greenhouse", "lever")`; `BoardConfig(type: str, name: str)` (frozen); `Config(boards: tuple[BoardConfig, ...], keywords: tuple[str, ...])` (frozen); `load_config(path: Path | None = None) -> Config` (default path is `boards.json` next to the module; keywords lowercased; raises `ValueError` for an unknown board type or an empty board list).

- [ ] **Step 1: Write the failing tests**

`services/jobfetcher/tests/test_config.py`:
```python
import json

import pytest

from jobfetcher.config import load_config


def _write(tmp_path, payload):
    path = tmp_path / "boards.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def test_default_config_lists_the_five_starter_boards():
    config = load_config()
    assert [(b.type, b.name) for b in config.boards] == [
        ("greenhouse", "stripe"),
        ("greenhouse", "figma"),
        ("greenhouse", "cloudflare"),
        ("lever", "spotify"),
        ("lever", "palantir"),
    ]
    assert "python" in config.keywords


def test_keywords_are_lowercased(tmp_path):
    path = _write(
        tmp_path,
        {"boards": [{"type": "lever", "name": "x"}], "keywords": ["QA", "SDET"]},
    )
    assert load_config(path).keywords == ("qa", "sdet")


def test_keywords_are_optional(tmp_path):
    path = _write(tmp_path, {"boards": [{"type": "lever", "name": "x"}]})
    assert load_config(path).keywords == ()


def test_unknown_board_type_is_rejected(tmp_path):
    path = _write(tmp_path, {"boards": [{"type": "nope", "name": "x"}]})
    with pytest.raises(ValueError, match="unknown board type 'nope'"):
        load_config(path)


def test_empty_board_list_is_rejected(tmp_path):
    path = _write(tmp_path, {"boards": []})
    with pytest.raises(ValueError, match="no boards"):
        load_config(path)
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest services/jobfetcher/tests/test_config.py -v`
Expected: collection ERROR `ModuleNotFoundError: No module named 'jobfetcher.config'`.

- [ ] **Step 3: Implement**

`services/jobfetcher/src/jobfetcher/boards.json`:
```json
{
  "boards": [
    {"type": "greenhouse", "name": "stripe"},
    {"type": "greenhouse", "name": "figma"},
    {"type": "greenhouse", "name": "cloudflare"},
    {"type": "lever", "name": "spotify"},
    {"type": "lever", "name": "palantir"}
  ],
  "keywords": ["automation", "sdet", "qa", "test", "testing", "infrastructure", "python"]
}
```

`services/jobfetcher/src/jobfetcher/config.py`:
```python
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

BOARD_TYPES = ("greenhouse", "lever")
DEFAULT_PATH = Path(__file__).with_name("boards.json")


@dataclass(frozen=True)
class BoardConfig:
    type: str
    name: str


@dataclass(frozen=True)
class Config:
    boards: tuple[BoardConfig, ...]
    keywords: tuple[str, ...]


def load_config(path: Path | None = None) -> Config:
    data = json.loads((path or DEFAULT_PATH).read_text(encoding="utf-8"))
    boards = []
    for entry in data["boards"]:
        if entry["type"] not in BOARD_TYPES:
            raise ValueError(
                f"unknown board type {entry['type']!r}; expected one of {BOARD_TYPES}"
            )
        boards.append(BoardConfig(entry["type"], entry["name"]))
    if not boards:
        raise ValueError("config has no boards")
    keywords = tuple(k.lower() for k in data.get("keywords", []))
    return Config(tuple(boards), keywords)
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python -m pytest services/jobfetcher/tests -v`
Expected: 12 passed.

- [ ] **Step 5: Commit**

```bash
git add services
git commit -m "feat(jobfetcher): add board and keyword configuration"
```

---

### Task 3: HTTP helper, JobSource base, Greenhouse source

**Files:**
- Create: `services/jobfetcher/src/jobfetcher/http.py`, `services/jobfetcher/src/jobfetcher/sources/__init__.py` (empty for now), `services/jobfetcher/src/jobfetcher/sources/base.py`, `services/jobfetcher/src/jobfetcher/sources/greenhouse.py`, `services/jobfetcher/tests/conftest.py`, `services/jobfetcher/tests/fixtures/greenhouse_jobs.json`, `services/jobfetcher/tests/fixtures/lever_postings.json`
- Test: `services/jobfetcher/tests/test_http.py`, `services/jobfetcher/tests/test_greenhouse.py`

**Interfaces:**
- Consumes: `JobPost`, `html_to_text` (Task 1).
- Produces: `jobfetcher.http.HttpGet = Callable[[str], bytes]`; `urllib_get(url: str, timeout: float = 25.0) -> bytes`; `JobSource` ABC (`kind: str`; `__init__(name: str, http_get: HttpGet)`; property `label -> f"{kind}:{name}"`; abstract `fetch() -> list[JobPost]`); `GreenhouseSource` (`kind = "greenhouse"`, class attr `URL`); test fixtures `greenhouse_payload`, `lever_payload` (bytes) and `fake_http` (`make(responses: dict[str, bytes | Exception]) -> get`, where `get.calls` lists requested URLs).

- [ ] **Step 1: Write the fixture files and conftest**

`services/jobfetcher/tests/fixtures/greenhouse_jobs.json` (shape verified against the live API on 2026-10-07):
```json
{
  "jobs": [
    {
      "id": 5426468004,
      "title": "Account Executive, Enterprise",
      "company_name": "Figma",
      "location": {"name": "San Francisco, CA"},
      "absolute_url": "https://boards.greenhouse.io/figma/jobs/5426468004",
      "updated_at": "2026-07-22T05:37:08-04:00",
      "first_published": "2025-01-28T18:57:29-05:00",
      "content": "&lt;div class=&quot;content-intro&quot;&gt;&lt;p&gt;We use Python &amp;amp; automation.&lt;/p&gt;&lt;/div&gt;"
    },
    {
      "id": 5426468005,
      "title": "SDET",
      "location": null,
      "absolute_url": "https://boards.greenhouse.io/figma/jobs/5426468005",
      "updated_at": "2026-07-23T05:37:08-04:00",
      "content": ""
    }
  ],
  "meta": {"total": 2}
}
```

`services/jobfetcher/tests/fixtures/lever_postings.json`:
```json
[
  {
    "id": "2193db3f-77c5-43b8-b030-8f92c9882bf1",
    "text": "Android Engineer - Experience",
    "categories": {"commitment": "Permanent", "department": "Engineering", "location": "Stockholm"},
    "hostedUrl": "https://jobs.lever.co/spotify/2193db3f-77c5-43b8-b030-8f92c9882bf1",
    "createdAt": 1782214185805,
    "descriptionPlain": "Build  Python\ntools.",
    "workplaceType": "hybrid"
  },
  {
    "id": "aaaa",
    "text": "QA Lead",
    "categories": {},
    "hostedUrl": "https://jobs.lever.co/spotify/aaaa",
    "createdAt": 1700000000000
  }
]
```

`services/jobfetcher/tests/conftest.py`:
```python
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
```

- [ ] **Step 2: Write the failing tests**

`services/jobfetcher/tests/test_http.py`:
```python
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
```

`services/jobfetcher/tests/test_greenhouse.py`:
```python
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
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/Scripts/python -m pytest services/jobfetcher/tests/test_http.py services/jobfetcher/tests/test_greenhouse.py -v`
Expected: collection ERRORs `ModuleNotFoundError: No module named 'jobfetcher.http'` / `jobfetcher.sources`.

- [ ] **Step 4: Implement**

`services/jobfetcher/src/jobfetcher/http.py`:
```python
from __future__ import annotations

import urllib.request
from collections.abc import Callable

HttpGet = Callable[[str], bytes]


def urllib_get(url: str, timeout: float = 25.0) -> bytes:
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "testbed-jobfetcher/0.1", "Accept": "application/json"},
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()
```

`services/jobfetcher/src/jobfetcher/sources/__init__.py`: empty file.

`services/jobfetcher/src/jobfetcher/sources/base.py`:
```python
from __future__ import annotations

from abc import ABC, abstractmethod

from jobfetcher.http import HttpGet
from jobfetcher.models import JobPost


class JobSource(ABC):
    """Strategy for one job-board API; subclasses set `kind` and implement `fetch`."""

    kind: str = ""

    def __init__(self, name: str, http_get: HttpGet) -> None:
        self.name = name
        self._http_get = http_get

    @property
    def label(self) -> str:
        return f"{self.kind}:{self.name}"

    @abstractmethod
    def fetch(self) -> list[JobPost]: ...
```

`services/jobfetcher/src/jobfetcher/sources/greenhouse.py`:
```python
from __future__ import annotations

import json
from typing import Any

from jobfetcher.models import JobPost
from jobfetcher.sources.base import JobSource
from jobfetcher.text import html_to_text


class GreenhouseSource(JobSource):
    kind = "greenhouse"
    URL = "https://boards-api.greenhouse.io/v1/boards/{name}/jobs?content=true"

    def fetch(self) -> list[JobPost]:
        payload = json.loads(self._http_get(self.URL.format(name=self.name)))
        return [self._to_post(item) for item in payload["jobs"]]

    def _to_post(self, item: dict[str, Any]) -> JobPost:
        return JobPost(
            id=str(item["id"]),
            source=self.label,
            company=item.get("company_name") or self.name,
            title=item["title"],
            location=(item.get("location") or {}).get("name", ""),
            url=item["absolute_url"],
            posted_at=item.get("first_published") or item.get("updated_at"),
            description=html_to_text(item.get("content") or ""),
        )
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv/Scripts/python -m pytest services/jobfetcher/tests -v`
Expected: 18 passed.

- [ ] **Step 6: Commit**

```bash
git add services
git commit -m "feat(jobfetcher): add HTTP helper, JobSource base and Greenhouse source"
```

---

### Task 4: Lever source and source registry

**Files:**
- Create: `services/jobfetcher/src/jobfetcher/sources/lever.py`
- Modify: `services/jobfetcher/src/jobfetcher/sources/__init__.py`
- Test: `services/jobfetcher/tests/test_lever.py`

**Interfaces:**
- Consumes: `JobSource`, `JobPost`, `BoardConfig`, `BOARD_TYPES`, `HttpGet`, test fixtures from Task 3.
- Produces: `LeverSource` (`kind = "lever"`, class attr `URL`); `jobfetcher.sources.SOURCE_TYPES: dict[str, type[JobSource]]` (keys `greenhouse`, `lever`); `create_source(board: BoardConfig, http_get: HttpGet) -> JobSource`.

- [ ] **Step 1: Write the failing tests**

`services/jobfetcher/tests/test_lever.py`:
```python
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
    assert first.company == "spotify"
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
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest services/jobfetcher/tests/test_lever.py -v`
Expected: collection ERROR `ModuleNotFoundError: No module named 'jobfetcher.sources.lever'`.

- [ ] **Step 3: Implement**

`services/jobfetcher/src/jobfetcher/sources/lever.py`:
```python
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from jobfetcher.models import JobPost
from jobfetcher.sources.base import JobSource


class LeverSource(JobSource):
    kind = "lever"
    URL = "https://api.lever.co/v0/postings/{name}?mode=json"

    def fetch(self) -> list[JobPost]:
        postings = json.loads(self._http_get(self.URL.format(name=self.name)))
        return [self._to_post(item) for item in postings]

    def _to_post(self, item: dict[str, Any]) -> JobPost:
        created = item.get("createdAt")
        posted_at = (
            datetime.fromtimestamp(created / 1000, tz=timezone.utc).isoformat()
            if created
            else None
        )
        return JobPost(
            id=str(item["id"]),
            source=self.label,
            company=self.name,
            title=item["text"],
            location=(item.get("categories") or {}).get("location", ""),
            url=item["hostedUrl"],
            posted_at=posted_at,
            description=" ".join((item.get("descriptionPlain") or "").split()),
        )
```

Replace `services/jobfetcher/src/jobfetcher/sources/__init__.py` with:
```python
from __future__ import annotations

from jobfetcher.config import BoardConfig
from jobfetcher.http import HttpGet
from jobfetcher.sources.base import JobSource
from jobfetcher.sources.greenhouse import GreenhouseSource
from jobfetcher.sources.lever import LeverSource

SOURCE_TYPES: dict[str, type[JobSource]] = {
    "greenhouse": GreenhouseSource,
    "lever": LeverSource,
}


def create_source(board: BoardConfig, http_get: HttpGet) -> JobSource:
    return SOURCE_TYPES[board.type](board.name, http_get)
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python -m pytest services/jobfetcher/tests -v`
Expected: 24 passed.

- [ ] **Step 5: Commit**

```bash
git add services
git commit -m "feat(jobfetcher): add Lever source and source registry"
```

---

### Task 5: Pipeline (isolation, dedupe, keyword tagging)

**Files:**
- Create: `services/jobfetcher/src/jobfetcher/pipeline.py`
- Test: `services/jobfetcher/tests/test_pipeline.py`

**Interfaces:**
- Consumes: `JobSource`, `JobPost`, `SourceResult`, `Config`, `create_source`, `HttpGet`.
- Produces: `build_sources(config: Config, http_get: HttpGet) -> list[JobSource]`; `fetch_source(source: JobSource) -> SourceResult` (never raises; error text is `"<ExceptionType>: <message>"[:300]`); `tag_keywords(job: JobPost, keywords: tuple[str, ...]) -> JobPost` (whole-word, case-insensitive match against `title + " " + description`, result ordered as in `keywords`); `run_pipeline(sources: list[JobSource], keywords: tuple[str, ...], now: datetime | None = None) -> dict` returning the output document from the Global Constraints.

- [ ] **Step 1: Write the failing tests**

`services/jobfetcher/tests/test_pipeline.py`:
```python
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
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest services/jobfetcher/tests/test_pipeline.py -v`
Expected: collection ERROR `ModuleNotFoundError: No module named 'jobfetcher.pipeline'`.

- [ ] **Step 3: Implement**

`services/jobfetcher/src/jobfetcher/pipeline.py`:
```python
from __future__ import annotations

import re
from dataclasses import replace
from datetime import datetime, timezone
from typing import Any

from jobfetcher.config import Config
from jobfetcher.http import HttpGet
from jobfetcher.models import JobPost, SourceResult
from jobfetcher.sources import create_source
from jobfetcher.sources.base import JobSource

MAX_ERROR = 300


def build_sources(config: Config, http_get: HttpGet) -> list[JobSource]:
    return [create_source(board, http_get) for board in config.boards]


def fetch_source(source: JobSource) -> SourceResult:
    try:
        jobs = source.fetch()
    except Exception as exc:
        return SourceResult(
            source.label, ok=False, error=f"{type(exc).__name__}: {exc}"[:MAX_ERROR]
        )
    return SourceResult(source.label, ok=True, jobs=jobs)


def tag_keywords(job: JobPost, keywords: tuple[str, ...]) -> JobPost:
    haystack = f"{job.title} {job.description}".lower()
    matched = [k for k in keywords if re.search(rf"\b{re.escape(k)}\b", haystack)]
    return replace(job, matched_keywords=matched)


def run_pipeline(
    sources: list[JobSource],
    keywords: tuple[str, ...],
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    results = [fetch_source(source) for source in sources]

    seen: set[tuple[str, str]] = set()
    jobs: list[dict[str, Any]] = []
    for result in results:
        for job in result.jobs:
            key = (job.source, job.id)
            if key in seen:
                continue
            seen.add(key)
            jobs.append(tag_keywords(job, keywords).to_dict())

    return {
        "generated_at": now.isoformat(),
        "sources": [result.status() for result in results],
        "jobs": jobs,
    }
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python -m pytest services/jobfetcher/tests -v`
Expected: 30 passed.

- [ ] **Step 5: Commit**

```bash
git add services
git commit -m "feat(jobfetcher): add pipeline with source isolation, dedupe and keyword tagging"
```

---

### Task 6: S3 storage and Lambda handler

**Files:**
- Create: `services/jobfetcher/src/jobfetcher/storage.py`, `services/jobfetcher/src/jobfetcher/handler.py`, `services/jobfetcher/events/dry-run.json`
- Modify: `services/jobfetcher/tests/conftest.py` (add `fake_s3`)
- Test: `services/jobfetcher/tests/test_storage_and_handler.py`

**Interfaces:**
- Consumes: `run_pipeline`, `build_sources`, `load_config`, `urllib_get`, `HttpGet`.
- Produces: `S3Store(bucket: str, client)` with `write(document: dict, date: str) -> list[str]` (puts `jobs/<date>.json` then `jobs/latest.json`, JSON body, `ContentType="application/json"`, returns the keys); `AllSourcesFailedError(RuntimeError)`; `lambda_handler(event, context=None, *, http_get=urllib_get, s3_client=None, now=None) -> dict` returning `{"dry_run": bool, "keys": [...] (absent when dry_run), "job_count": int, "sources": [...]}`; raises `AllSourcesFailedError` (and writes nothing) when no source succeeded; requires env `BUCKET_NAME` unless `event["dry_run"]` is true. Handler path for SAM: `jobfetcher.handler.lambda_handler`.

- [ ] **Step 1: Add the `fake_s3` fixture**

Append to `services/jobfetcher/tests/conftest.py`:
```python
class _FakeS3:
    def __init__(self):
        self.puts = []

    def put_object(self, **kwargs):
        self.puts.append(kwargs)


@pytest.fixture
def fake_s3():
    return _FakeS3()
```

- [ ] **Step 2: Write the failing tests**

`services/jobfetcher/events/dry-run.json`:
```json
{"dry_run": true}
```

`services/jobfetcher/tests/test_storage_and_handler.py`:
```python
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
```

- [ ] **Step 3: Run to verify failure**

Run: `.venv/Scripts/python -m pytest services/jobfetcher/tests/test_storage_and_handler.py -v`
Expected: collection ERROR `ModuleNotFoundError: No module named 'jobfetcher.handler'`.

- [ ] **Step 4: Implement**

`services/jobfetcher/src/jobfetcher/storage.py`:
```python
from __future__ import annotations

import json
from typing import Any


class S3Store:
    def __init__(self, bucket: str, client: Any) -> None:
        self._bucket = bucket
        self._client = client

    def write(self, document: dict[str, Any], date: str) -> list[str]:
        body = json.dumps(document, ensure_ascii=False).encode("utf-8")
        keys = [f"jobs/{date}.json", "jobs/latest.json"]
        for key in keys:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=body,
                ContentType="application/json",
            )
        return keys
```

`services/jobfetcher/src/jobfetcher/handler.py`:
```python
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from jobfetcher.config import load_config
from jobfetcher.http import HttpGet, urllib_get
from jobfetcher.pipeline import build_sources, run_pipeline
from jobfetcher.storage import S3Store


class AllSourcesFailedError(RuntimeError):
    """Every configured board failed; nothing is written so latest.json stays intact."""


def lambda_handler(
    event: Any,
    context: Any = None,
    *,
    http_get: HttpGet = urllib_get,
    s3_client: Any = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    config = load_config()
    document = run_pipeline(build_sources(config, http_get), config.keywords, now)
    summary = {"job_count": len(document["jobs"]), "sources": document["sources"]}
    print(json.dumps({"event": "jobfetcher.run", **summary}))

    if not any(source["ok"] for source in document["sources"]):
        raise AllSourcesFailedError(f"all {len(document['sources'])} sources failed")

    if isinstance(event, dict) and event.get("dry_run"):
        return {"dry_run": True, **summary}

    bucket = os.environ["BUCKET_NAME"]
    if s3_client is None:
        import boto3

        s3_client = boto3.client("s3")
    keys = S3Store(bucket, s3_client).write(document, now.date().isoformat())
    return {"dry_run": False, "keys": keys, **summary}
```

- [ ] **Step 5: Run to verify pass**

Run: `.venv/Scripts/python -m pytest services/jobfetcher/tests -v`
Expected: 36 passed.

- [ ] **Step 6: Commit**

```bash
git add services
git commit -m "feat(jobfetcher): add S3 store and Lambda handler with dry-run mode"
```

---

### Task 7: SAM template, samconfig, template guard tests

**Files:**
- Create: `services/jobfetcher/template.yaml`, `services/jobfetcher/samconfig.toml`
- Modify: `.gitignore` (add `.aws-sam/`)
- Test: `services/jobfetcher/tests/test_template.py`

**Interfaces:**
- Consumes: handler path `jobfetcher.handler.lambda_handler`, env var `BUCKET_NAME`.
- Produces: SAM stack `testbed-jobfetcher` with resources `JobsBucket` and `JobFetcherFunction`, outputs `BucketName` and `FunctionName`; `samconfig.toml` defaults so `sam deploy` needs no flags. The tests are static guards on the template (security and sizing regressions), runnable offline.

- [ ] **Step 1: Write the failing tests**

`services/jobfetcher/tests/test_template.py`:
```python
from pathlib import Path

import pytest
import yaml

TEMPLATE = Path(__file__).parents[1] / "template.yaml"


class _CfnLoader(yaml.SafeLoader):
    pass


def _ignore_tag(loader, tag_suffix, node):
    if isinstance(node, yaml.ScalarNode):
        return loader.construct_scalar(node)
    if isinstance(node, yaml.SequenceNode):
        return loader.construct_sequence(node)
    return loader.construct_mapping(node)


_CfnLoader.add_multi_constructor("!", _ignore_tag)


@pytest.fixture(scope="module")
def template():
    return yaml.load(TEMPLATE.read_text(encoding="utf-8"), Loader=_CfnLoader)


def test_is_a_sam_template(template):
    assert template["Transform"] == "AWS::Serverless-2016-10-31"


def test_function_defaults_match_the_spec(template):
    defaults = template["Globals"]["Function"]
    assert defaults["Runtime"] == "python3.13"
    assert defaults["Architectures"] == ["x86_64"]
    assert defaults["MemorySize"] == 512
    assert defaults["Timeout"] == 120


def test_function_wiring(template):
    props = template["Resources"]["JobFetcherFunction"]["Properties"]
    assert props["CodeUri"] == "src/"
    assert props["Handler"] == "jobfetcher.handler.lambda_handler"
    assert props["Environment"]["Variables"]["BUCKET_NAME"] == "JobsBucket"


def test_runtime_role_can_only_put_objects_under_jobs(template):
    props = template["Resources"]["JobFetcherFunction"]["Properties"]
    statements = [s for policy in props["Policies"] for s in policy["Statement"]]
    assert len(statements) == 1
    statement = statements[0]
    assert statement["Effect"] == "Allow"
    assert statement["Action"] == "s3:PutObject"
    assert statement["Resource"].endswith("/jobs/*")


def test_function_runs_on_a_daily_schedule(template):
    events = template["Resources"]["JobFetcherFunction"]["Properties"]["Events"]
    schedules = [e for e in events.values() if e["Type"] == "Schedule"]
    assert len(schedules) == 1
    assert schedules[0]["Properties"]["Schedule"].startswith("cron(")


def test_bucket_is_private_encrypted_and_expires_dated_objects_only(template):
    props = template["Resources"]["JobsBucket"]["Properties"]
    assert props["PublicAccessBlockConfiguration"] == {
        "BlockPublicAcls": True,
        "BlockPublicPolicy": True,
        "IgnorePublicAcls": True,
        "RestrictPublicBuckets": True,
    }
    encryption = props["BucketEncryption"]["ServerSideEncryptionConfiguration"][0]
    assert encryption["ServerSideEncryptionByDefault"]["SSEAlgorithm"] == "AES256"
    rule = props["LifecycleConfiguration"]["Rules"][0]
    assert rule["Status"] == "Enabled"
    assert rule["Prefix"] == "jobs/20"  # dated objects only, never latest.json
    assert rule["ExpirationInDays"] == 30


def test_outputs_expose_bucket_and_function_names(template):
    assert set(template["Outputs"]) == {"BucketName", "FunctionName"}
```

- [ ] **Step 2: Run to verify failure**

Run: `.venv/Scripts/python -m pytest services/jobfetcher/tests/test_template.py -v`
Expected: FAIL with `FileNotFoundError` for `template.yaml`.

- [ ] **Step 3: Implement**

`services/jobfetcher/template.yaml`:
```yaml
AWSTemplateFormatVersion: "2010-09-09"
Transform: AWS::Serverless-2016-10-31
Description: testbed job-fetcher Lambda, fetches public job posts daily and stores them in S3

Globals:
  Function:
    Runtime: python3.13
    Architectures:
      - x86_64
    MemorySize: 512
    Timeout: 120

Resources:
  JobsBucket:
    Type: AWS::S3::Bucket
    Properties:
      BucketEncryption:
        ServerSideEncryptionConfiguration:
          - ServerSideEncryptionByDefault:
              SSEAlgorithm: AES256
      PublicAccessBlockConfiguration:
        BlockPublicAcls: true
        BlockPublicPolicy: true
        IgnorePublicAcls: true
        RestrictPublicBuckets: true
      LifecycleConfiguration:
        Rules:
          - Id: ExpireDatedSnapshots
            Status: Enabled
            # "jobs/20" matches jobs/2026-10-07.json but never jobs/latest.json
            Prefix: jobs/20
            ExpirationInDays: 30

  JobFetcherFunction:
    Type: AWS::Serverless::Function
    Properties:
      CodeUri: src/
      Handler: jobfetcher.handler.lambda_handler
      Description: Fetch Greenhouse and Lever job posts and write them to S3
      Environment:
        Variables:
          BUCKET_NAME: !Ref JobsBucket
      Policies:
        - Version: "2012-10-17"
          Statement:
            - Effect: Allow
              Action: s3:PutObject
              Resource: !Sub "${JobsBucket.Arn}/jobs/*"
      Events:
        Daily:
          Type: Schedule
          Properties:
            Schedule: cron(0 5 * * ? *)
            Description: Daily fetch at 05:00 UTC

Outputs:
  BucketName:
    Description: Bucket holding jobs/<date>.json and jobs/latest.json
    Value: !Ref JobsBucket
  FunctionName:
    Description: Deployed Lambda function name
    Value: !Ref JobFetcherFunction
```

`services/jobfetcher/samconfig.toml`:
```toml
version = 0.1

[default.global.parameters]
stack_name = "testbed-jobfetcher"

[default.build.parameters]
cached = false

[default.deploy.parameters]
region = "eu-north-1"
capabilities = "CAPABILITY_IAM"
resolve_s3 = true
confirm_changeset = true
```

Append to `.gitignore`:
```
.aws-sam/
```

- [ ] **Step 4: Run to verify pass**

Run: `.venv/Scripts/python -m pytest services/jobfetcher/tests -v`
Expected: 43 passed.

- [ ] **Step 5: Commit**

```bash
git add services .gitignore
git commit -m "feat(jobfetcher): add SAM template, samconfig and template guard tests"
```

---

### Task 8 (MANUAL): AWS setup, validate, deploy, verify

**Executor:** the controller guides the user step by step; the **user** runs every command that needs AWS credentials (use `! <command>` in the prompt). The assistant never asks for, reads, or pastes keys. No subagent is dispatched for this task. Ledger it in the controller's progress file as `Task 8: complete (stack testbed-jobfetcher deployed, latest.json verified)`.

**Files:** none created by tools; the deployed stack and `jobs/latest.json` are the deliverable. Record the outputs (bucket name, function name) in the Task 9 docs.

- [ ] **Step 1: Install the CLIs (user)**

```bash
winget install -e --id Amazon.AWSCLI
winget install -e --id Amazon.SAM-CLI
```
Open a **new** terminal afterwards, then check: `aws --version` and `sam --version`. If winget fails, install both MSIs from the AWS documentation pages for "Installing the AWS CLI" and "Installing the AWS SAM CLI".

- [ ] **Step 2: Create a dedicated deploy user in the AWS console (user)**

1. Sign in to the AWS console with your account, enable MFA on the root user if not done, and open **IAM → Users → Create user** named `testbed-deployer` (no console access).
2. Attach these managed policies: `AWSCloudFormationFullAccess`, `AWSLambda_FullAccess`, `AmazonS3FullAccess`, `AmazonEventBridgeFullAccess`, `IAMFullAccess`. (Broad on purpose for a sandbox; see Ruling C. Tighten in Phase 4.)
3. **Security credentials → Create access key → "Command Line Interface"**. Keep the page open for the next step; never paste the keys into the chat.

- [ ] **Step 3: Configure a named profile (user)**

```bash
aws configure --profile testbed
```
Enter the access key id and secret from the console, region `eu-north-1`, output `json`. Then verify and delete the console tab:
```bash
aws sts get-caller-identity --profile testbed
```
Expected: JSON with the `testbed-deployer` ARN (not root).

- [ ] **Step 4: Validate and build offline-first (user or controller)**

```bash
cd services/jobfetcher
sam validate --lint --region eu-north-1
sam build
```
Expected: `template.yaml is a valid SAM Template` and `Build Succeeded`. Fix any lint finding in `template.yaml`, re-run `.venv/Scripts/python -m pytest services/jobfetcher/tests/test_template.py`, and commit the fix.

- [ ] **Step 5: Local invoke in dry-run mode (user; needs Docker running, no AWS credentials)**

```bash
sam local invoke JobFetcherFunction --event events/dry-run.json
```
Expected: the printed result has `"dry_run": true`, `"job_count"` in the hundreds or thousands, and `sources` showing five entries with `"ok": true`. If a source shows `ok: false`, note its error; one failing board is tolerated, but investigate if all fail (network or Docker proxy).

- [ ] **Step 6: Deploy (user)**

```bash
sam deploy --profile testbed
```
When shown the change set, review it (one bucket, one function, one role, one schedule rule) and answer `y`. Expected: `Successfully created/updated stack - testbed-jobfetcher in eu-north-1`. Copy the `BucketName` and `FunctionName` from the Outputs.

- [ ] **Step 7: Invoke the deployed function and verify the output (user)**

```bash
aws lambda invoke --function-name <FunctionName> --payload '{}' --cli-binary-format raw-in-base64-out out.json --profile testbed --region eu-north-1
cat out.json
aws s3 ls s3://<BucketName>/jobs/ --profile testbed --region eu-north-1
aws s3 cp s3://<BucketName>/jobs/latest.json latest.json --profile testbed --region eu-north-1
python -c "import json; d=json.load(open('latest.json', encoding='utf-8')); print(d['generated_at'], len(d['jobs']), [s['ok'] for s in d['sources']])"
```
Expected: `out.json` has `"dry_run": false` and two keys; the bucket lists `jobs/<today>.json` and `jobs/latest.json`; the last command prints a timestamp, a job count, and five booleans (all true on a healthy day). Delete `out.json` and `latest.json` afterwards (they are not for the repo).

- [ ] **Step 8: Confirm the schedule and logs (user)**

```bash
aws logs tail /aws/lambda/<FunctionName> --since 15m --profile testbed --region eu-north-1
```
Expected: the `jobfetcher.run` JSON line from Step 7. The daily EventBridge rule runs at 05:00 UTC. To remove everything later: `sam delete --profile testbed` (the bucket must be emptied first, `aws s3 rm s3://<BucketName> --recursive`).

---

### Task 9: Docs, final verification, integration

**Files:**
- Modify: `README.md`, `CLAUDE.md`, `docs/superpowers/specs/2026-10-06-testbed-design.md` (only if Task 8 changed any decision)

**Interfaces:**
- Consumes: deployed bucket and function names recorded in Task 8; everything from Tasks 1-7.
- Produces: truthful docs; Phase 2 marked built; branch ready to open a PR into `phase-1-core`'s base once Phase 1 merges.

- [ ] **Step 1: Run the full suite**

Run: `.venv/Scripts/python -m pytest services/jobfetcher/tests -v` and `.venv/Scripts/python -m pytest testbed-core/tests -q`
Expected: 43 passed in `services/jobfetcher`, 62 passed in `testbed-core`.

- [ ] **Step 2: Update README.md**

- Status table: Phase 2 → `**Built, deployed to eu-north-1 and verified**` (only if Task 8 completed; otherwise `Built; deploy pending`).
- Add a "Job-fetcher Lambda" section: what it does, the S3 output document shape (copy from Global Constraints), how to run the service tests (`.venv/Scripts/python -m pytest services/jobfetcher/tests`), the `dry_run` event, `sam validate/build/deploy` commands with `--profile testbed`, and a cost note (free-tier sized, `sam delete` to remove).
- Move the `jobfetcher` bullet in "Planned (later phases)" so it describes only the adapter and contract tests (Phase 3).
- Repository layout: add `services/jobfetcher/`.

- [ ] **Step 3: Update CLAUDE.md**

- Status paragraph: Phase 2 built.
- Commands: add the service test command, `sam validate --lint`, `sam build`, `sam local invoke JobFetcherFunction --event events/dry-run.json`, `sam deploy --profile testbed` (all from `services/jobfetcher`).
- Architecture: one bullet each for "sources are `JobSource` strategies; one failing source is isolated and reported in `sources`, run fails only if all fail", "handler accepts `{"dry_run": true}`", and "S3 keys: `jobs/<date>.json`, `jobs/latest.json`; lifecycle only expires dated keys".
- Never record credentials, account ids, or the access key anywhere in the repo.

- [ ] **Step 4: Commit**

```bash
git add README.md CLAUDE.md docs
git commit -m "docs: record Phase 2 job-fetcher service, commands and deployment"
```

- [ ] **Step 5: Integration (controller, with the user's consent)**

Do not push or merge without explicit approval. Offer: push `phase-2-lambda` and open a PR (base `phase-1-core` until Phase 1 merges, then `master`), or keep the branch local.
