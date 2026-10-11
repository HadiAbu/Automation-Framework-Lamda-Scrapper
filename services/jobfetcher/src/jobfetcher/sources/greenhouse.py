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
            company=item.get("company_name") or self.display_name,
            title=item["title"],
            location=(item.get("location") or {}).get("name", ""),
            url=item["absolute_url"],
            posted_at=item.get("first_published") or item.get("updated_at"),
            description=html_to_text(item.get("content") or ""),
        )
