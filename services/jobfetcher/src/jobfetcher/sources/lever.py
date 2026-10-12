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
            company=self.display_name,
            title=item["text"],
            location=(item.get("categories") or {}).get("location", ""),
            url=item["hostedUrl"],
            posted_at=posted_at,
            description=" ".join((item.get("descriptionPlain") or "").split()),
        )
