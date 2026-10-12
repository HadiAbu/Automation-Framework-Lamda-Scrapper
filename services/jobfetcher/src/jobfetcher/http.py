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
