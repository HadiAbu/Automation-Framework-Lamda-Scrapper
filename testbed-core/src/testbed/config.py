from __future__ import annotations

import os
from collections.abc import Mapping

from testbed.errors import MissingConfigError


class EnvConfig:
    def __init__(self, values: Mapping[str, str] | None = None) -> None:
        self._values: Mapping[str, str] = os.environ if values is None else values

    def get(self, key: str, default: str | None = None) -> str | None:
        return self._values.get(key, default)

    def require(self, key: str) -> str:
        value = self._values.get(key)
        if not value:
            raise MissingConfigError(f"required setting {key!r} is not set")
        return value
