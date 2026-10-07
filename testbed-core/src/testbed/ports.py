from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from testbed.reporting.models import RunReport


@runtime_checkable
class Environment(Protocol):
    def get(self, key: str, default: str | None = None) -> str | None: ...

    def require(self, key: str) -> str: ...


class ProjectAdapter(ABC):
    """Port every project under test implements."""

    name: str = ""

    @abstractmethod
    def setup(self) -> None: ...

    @abstractmethod
    def health_check(self) -> bool: ...

    @abstractmethod
    def client(self) -> Any:
        """Return an object tests use to drive the project."""

    @abstractmethod
    def teardown(self) -> None: ...

    def describe(self) -> dict[str, str]:
        return {"name": self.name}


class ReportSink(ABC):
    """Port for publishing a finished run report."""

    @abstractmethod
    def publish(self, report: RunReport) -> str | None:
        """Publish the report; return a location (path or URL) if there is one."""
