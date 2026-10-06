# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Status

Greenfield. As of 2026-10-06 the repo contains only the approved design spec at `docs/superpowers/specs/2026-10-06-testbed-design.md`; no code exists yet. Read the spec before building anything. Update this file as real build/test commands and structure land (commands below are the intended ones, not yet verified).

## What this is

`testbed`: a multi-project test-automation platform, built as a portfolio piece for an automation-infrastructure engineer role (Python, OOD, AWS, Docker, CI). Python 3.13, pytest, AWS SAM, GitHub Actions, Notion for reporting.

## Architecture (big picture)

Hexagonal core + one entry-point plugin per project, all delivered as a pytest plugin:

- `testbed-core/` defines ports (`ProjectAdapter`, `ReportSink`, `Environment`) and the pytest fixtures that wire them (composition root). Tests depend on ports only.
- Core **never imports a project**. `discovery.py` loads projects through `importlib.metadata.entry_points(group="testbed.projects")`. Adding a project = a new package that registers its adapter and tests via that entry point, with no core changes. Preserve this invariant.
- Fixture scopes: session (`env_config`, `aws_session`, `report_sink`), module (`adapter`, resolved by project name), function (`client`, `artifact_dir`).
- Reporting: pytest hooks build a `RunReport`; sinks are `JsonSink` and `NotionSink`. Flaky tests (rerun once) must be tagged in the report, never silently passed.
- `FakeAdapter` lives in core so the framework is testable offline.
- Projects under test: `projects/jobfetcher` (adapter invokes the deployed Lambda and reads S3) and `projects/publicapi` (second demo target proving reuse).
- `services/jobfetcher/` is the Lambda being tested: `JobSource` strategies (Greenhouse, Lever) normalize to `JobPost` and write `jobs/<date>.json` to S3. Infra is AWS SAM (`template.yaml`: Lambda, daily EventBridge schedule, S3, IAM, GitHub OIDC role). The Lambda runs on its own schedule; GitHub Actions only tests it.
- CI: `test.yml` runs `pytest -n auto` in Docker and `NotionSink` writes a row to the "Test Runs" Notion DB plus a report page, with the link in the job summary. `deploy.yml` runs `sam build && sam deploy` via OIDC (no long-lived AWS keys).

## Intended commands

```
pytest -n auto                      # full suite (parallel)
pytest path/to/test.py::test_name   # single test
sam local invoke                    # run the Lambda locally
sam build && sam deploy             # deploy
docker run testbed pytest -n auto   # containerized run
```

## Workflow conventions

- Develop each phase (1 core, 2 Lambda+SAM, 3 project plugins+Docker, 4 CI+Notion, 5 docs) on its own branch; merge to `main` with `--no-ff` and never delete the phase branch.
- Never push to a remote without explicit per-instance approval from the user.
- Job boards to poll live in a config file, not in code.
- Required secrets for CI: `NOTION_TOKEN`, `NOTION_DB_ID`, AWS role ARN.
