from __future__ import annotations

from typing import Any

from testbed.ports import Environment, ProjectAdapter


class FakeClient:
    def echo(self, value: Any) -> Any:
        return value


class FakeAdapter(ProjectAdapter):
    """In-memory adapter that lets the framework be tested offline."""

    name = "fake"

    def __init__(self, env: Environment) -> None:
        self.env = env
        self.events: list[str] = []

    def setup(self) -> None:
        self.events.append("setup")

    def health_check(self) -> bool:
        return True

    def client(self) -> FakeClient:
        return FakeClient()

    def teardown(self) -> None:
        self.events.append("teardown")
