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
