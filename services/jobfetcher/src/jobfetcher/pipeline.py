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
