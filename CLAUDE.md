# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

Phase 1 (`testbed-core`) is implemented: ports, entry-point discovery, fixtures, JSON reporting, collector and flaky retry. Later phases (Lambda + SAM, project plugins + Docker, CI + Notion) are not built yet. The design spec is at `docs/superpowers/specs/2026-10-06-testbed-design.md`; read it before building anything.

## What this is

`testbed`: a multi-project test-automation platform, built as a portfolio piece for an automation-infrastructure engineer role (Python, OOD, AWS, Docker, CI). Python 3.13, pytest, AWS SAM, GitHub Actions, Notion for reporting.

## Architecture (big picture)

Hexagonal core + one entry-point plugin per project, all delivered as a pytest plugin:

- `testbed-core/` defines ports (`ProjectAdapter`, `ReportSink`, `Environment`) and the pytest fixtures that wire them (composition root). Tests depend on ports only.
- Core **never imports a project**. `discovery.py` loads projects through `importlib.metadata.entry_points(group="testbed.projects")`. Adding a project = a new package that registers its adapter and tests via that entry point, with no core changes. Preserve this invariant.
- Fixture scopes: session (`env_config`, `registry`, `aws_session`, `report_sink`), module (`adapter`, resolved by project name), function (`client`, `artifact_dir`).
- Reporting: pytest hooks build a `RunReport`; sinks are `JsonSink` (built) and `NotionSink` (planned, Phase 4). Flaky tests (rerun once) must be tagged in the report, never silently passed.
- Report data travels on `report.user_properties` (`PROJECT_KEY`/`FLAKY_KEY`), so collection is designed to be xdist-safe (untested until Phase 3); `ReportCollector` only publishes on the controller process.
- Teardown failures appear as separate `<nodeid> [teardown]` failed entries in the report. For a retried test, teardown failures from its discarded attempts are reported the same way.
- `FakeAdapter` lives in core so the framework is testable offline.
- Projects under test: `projects/jobfetcher` (adapter invokes the deployed Lambda and reads S3) and `projects/publicapi` (second demo target proving reuse).
- `services/jobfetcher/` is the Lambda being tested: `JobSource` strategies (Greenhouse, Lever) normalize to `JobPost` and write `jobs/<date>.json` to S3. Infra is AWS SAM (`template.yaml`: Lambda, daily EventBridge schedule, S3, IAM, GitHub OIDC role). The Lambda runs on its own schedule; GitHub Actions only tests it.
- CI (planned, Phase 4): `test.yml` runs `pytest -n auto` in Docker and `NotionSink` writes a row to the "Test Runs" Notion DB plus a report page, with the link in the job summary. `deploy.yml` runs `sam build && sam deploy` via OIDC (no long-lived AWS keys).

## Commands

```
python -m venv .venv && .venv/Scripts/python -m pip install -e testbed-core   # setup (re-run after changing pyproject entry points)
.venv/Scripts/python -m pytest testbed-core/tests                              # core suite
.venv/Scripts/python -m pytest testbed-core/tests/test_retry.py::test_name     # single test
```

Users get 1 retry by default; the core suite pins `--testbed-retries=0` in `testbed-core/pyproject.toml` addopts. Options: `--testbed-retries N`, ini `testbed_project`, ini `testbed_report_dir`.

### Planned (later phases)

```
pytest -n auto                      # full suite (parallel)
sam local invoke                    # run the Lambda locally
sam build && sam deploy             # deploy
docker run testbed pytest -n auto   # containerized run
```

## Workflow conventions

- Develop each phase (1 core, 2 Lambda+SAM, 3 project plugins+Docker, 4 CI+Notion, 5 docs) on its own branch; merge to `main` with `--no-ff` and never delete the phase branch.
- Never push to a remote without explicit per-instance approval from the user.
- Job boards to poll live in a config file, not in code.
- Required secrets for CI: `NOTION_TOKEN`, `NOTION_DB_ID`, AWS role ARN.
