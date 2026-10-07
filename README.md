# testbed

A multi-project test-automation platform, delivered as a **pytest plugin**. Teams don't write their own test infrastructure: each project ships a small *adapter*, registers it through a Python entry point, and gets shared fixtures, structured reporting and flaky-test detection for free. The core never imports any project.

Built as a portfolio piece for an automation-infrastructure engineering role (Python, OOD, AWS, Docker, CI).

## Status

| Phase | Scope | State |
|---|---|---|
| 1 | Core framework: ports, discovery, fixtures, JSON reporting, flaky retry | **Built and tested** (62 tests) |
| 2 | Job-fetcher Lambda + AWS SAM | Planned |
| 3 | Project plugins (`jobfetcher`, `publicapi`) + Docker + parallel runs | Planned |
| 4 | GitHub Actions CI + Notion reporting | Planned |
| 5 | Docs and polish | Planned |

Only Phase 1 exists in code today. Everything below marked *(planned)* is designed in [`docs/superpowers/specs/2026-10-06-testbed-design.md`](docs/superpowers/specs/2026-10-06-testbed-design.md) but not implemented yet.

## Architecture

Hexagonal ("ports and adapters") core. Tests depend on abstract ports; concrete projects plug in from outside.

```
          your tests (use fixtures only)
                    │
      ┌─────────────▼─────────────┐
      │   testbed-core  (plugin)   │
      │   ports      ProjectAdapter · ReportSink · Environment
      │   discovery  finds projects at runtime
      │   fixtures   composition root (scoped wiring)
      │   collector  builds the run report
      │   retry      reruns failures, tags flaky passes
      └─────────────┬─────────────┘
        entry-point group  "testbed.projects"
         ┌──────────┴───────────┐
   jobfetcher adapter     publicapi adapter      ← separate packages (planned)
```

- **Ports** (`testbed.ports`): `ProjectAdapter` (`setup`, `health_check`, `client`, `teardown`, `describe`), `ReportSink` (`publish`) and `Environment` (`get`, `require`).
- **Discovery** (`testbed.discovery`): loads adapter factories from the `testbed.projects` entry-point group. The core **never imports a project**.
- **Fixtures** (`testbed.fixtures`): the composition root, layered by scope.
- **Reporting** (`testbed.reporting`): a `ReportCollector` plugin object turns pytest's per-test reports into a `RunReport` and publishes it through a `ReportSink` (`JsonSink` today; a Notion sink is *planned*).
- **Retry** (`testbed.retry`): reruns a failing test call; a pass on retry is reported as `flaky`, never as a plain pass.

### Fixtures

| Fixture | Scope | What it gives you |
|---|---|---|
| `env_config` | session | `EnvConfig` over the process environment (`get` / `require`) |
| `registry` | session | `{project name: adapter factory}` from entry points (override it in a `conftest.py` to inject fakes) |
| `aws_session` | session | `boto3.Session` using `AWS_REGION`; fails loudly if boto3 is missing (`pip install "testbed-core[aws]"`) |
| `report_sink` | session | The sink the run report is published through |
| `adapter` | module | The project adapter, set up, health-checked, and torn down after the module |
| `client` | function | `adapter.client()`, the object tests use to drive the project |
| `artifact_dir` | function | A per-test directory under `<report dir>/artifacts/` |

## Quickstart

Requires Python 3.13+.

```bash
python -m venv .venv
.venv/Scripts/python -m pip install -e testbed-core      # Windows (Git Bash); use .venv/bin/python on Linux/macOS
.venv/Scripts/python -m pytest testbed-core/tests        # run the core suite
```

Re-run the `pip install -e` step whenever you change entry points in a `pyproject.toml`: entry points are baked in at install time.

Run a single test:

```bash
.venv/Scripts/python -m pytest testbed-core/tests/test_retry.py::test_pass_on_retry_is_reported_as_flaky_not_passed
```

## Using it

A test module selects its project with a module-level marker (a marker on a single test or class is **not** honored by the `adapter` fixture):

```python
import pytest

pytestmark = pytest.mark.project("fake")   # the built-in offline FakeAdapter

def test_echo(client):
    assert client.echo("hi") == "hi"
```

Or set a default for the whole suite in your pytest ini file:

```ini
[pytest]
testbed_project = fake
testbed_report_dir = reports
```

### Options

| Option | Default | Meaning |
|---|---|---|
| `--testbed-retries N` | `1` | Rerun a failing test call up to N times; a pass on retry is tagged `flaky`. `0` disables. Only call-phase failures are retried, not setup errors. |
| ini `testbed_project` | *(none)* | Default project when a module has no marker |
| ini `testbed_report_dir` | `reports` | Where `report.json` and artifacts are written (relative to the rootdir) |

The framework's own suite pins `--testbed-retries=0` so it never masks its own flakiness.

## Adding a new project

The core is never edited. Five steps:

1. Create a package with an adapter implementing `ProjectAdapter`:

   ```python
   from testbed.ports import Environment, ProjectAdapter

   class OrdersAdapter(ProjectAdapter):
       name = "orders"

       def __init__(self, env: Environment) -> None:
           self.base_url = env.require("ORDERS_URL")

       def setup(self) -> None: ...
       def health_check(self) -> bool: ...
       def client(self):
           return OrdersClient(self.base_url)
       def teardown(self) -> None: ...
   ```

2. Register it in that package's `pyproject.toml`:

   ```toml
   [project.entry-points."testbed.projects"]
   orders = "orders_testbed.adapter:OrdersAdapter"
   ```

3. `pip install -e` the package.
4. Write tests with `pytestmark = pytest.mark.project("orders")` and use the `client` fixture.
5. Run `pytest`. Reporting and flaky detection are already there.

## The run report

Every run writes `<report dir>/report.json` and prints its location:

```json
{
  "started_at": "2026-10-07T09:00:00+00:00",
  "duration": 1.234,
  "summary": {"total": 4, "passed": 2, "failed": 0, "skipped": 1, "flaky": 1},
  "results": [
    {"nodeid": "t.py::test_x", "project": "fake", "outcome": "flaky",
     "duration": 0.12, "message": "<first failure text>"}
  ]
}
```

Outcomes are `passed`, `failed`, `skipped` and `flaky`. Setup, teardown and collection errors are recorded as separate failed entries (`<nodeid> [teardown]`, `<nodeid> [collect]`), so the report agrees with pytest's exit status. A failing sink is surfaced in the terminal summary and does not crash the run.

## Design decisions

| Decision | Why | Rejected alternative |
|---|---|---|
| pytest plugin | Reuses collection, assertions and parametrization | A custom runner that reimplements pytest |
| Ports and adapters | New projects need no core change; the same tests can target a fake, local or cloud adapter | A shared helper library that is copied between repos |
| Entry-point discovery | Teams ship adapters independently of the core | A hard-coded registry in core |
| Fixtures as composition root | Natural scoping and teardown | A bespoke DI container |
| Report data carried on `report.user_properties` | Designed to survive pytest-xdist worker → controller transport | A global collector object |
| Flaky is tagged, not hidden | A silent retry hides real instability | A plain rerun plugin |

## Known limitations

- The project is selected per module only.
- A strict xpass can be retried, and retrying the last test of a scope re-creates session and module fixtures.
- Parallel (`pytest-xdist`) operation is designed for but **not yet verified** (Phase 3).
- The terminal shows a flaky test as `PASSED`; only `report.json` marks it `flaky`.
- `--collect-only` still writes an empty report.

## Planned (later phases)

- **`jobfetcher`**: an AWS Lambda on an EventBridge schedule that fetches job posts from public Greenhouse/Lever board APIs and writes `jobs/<date>.json` to S3, deployed with AWS SAM.
- **`publicapi`**: a second, small target proving the platform is reusable.
- **CI**: GitHub Actions runs the suite in Docker (`pytest -n auto`) and publishes each run to a Notion database with a shareable report link.

## Repository layout

```
testbed-core/            the pytest plugin (src layout)
  src/testbed/           ports, discovery, fixtures, plugin, retry, reporting/
  tests/                 the framework's own suite (pytester-based)
docs/superpowers/
  specs/                 design spec
  plans/                 phase implementation plans
CLAUDE.md                guidance for Claude Code working in this repo
```

Each phase is developed on its own branch and merged with `--no-ff`; phase branches are kept as rollback anchors.

## Stack

Python 3.13, pytest, setuptools (src layout). Planned: AWS SAM (Lambda, EventBridge, S3), Docker, GitHub Actions, Notion API.

## License

See [`LICENSE`](LICENSE).
