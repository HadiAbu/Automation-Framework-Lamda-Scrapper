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
