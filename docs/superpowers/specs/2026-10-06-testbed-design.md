# Plan: `testbed` — multi-project automation platform (interview portfolio piece)

## Context
Prep for an automation-infrastructure engineer role (Python, OOP/OOD, automation frameworks, AWS, Docker, CI, mentoring). Build a small, real, deployed platform showing: reusable framework design, multiple projects on it, cloud + CI, and results reporting. Directory `C:\Users\borni\CLaude\amazon-automation` is empty (greenfield).

Decisions made with user: platform + 2 demo projects; free public job-board JSON APIs (Greenhouse/Lever); EventBridge-scheduled Lambda with Actions only testing; Notion DB row per run + report page; AWS SAM; **hexagonal core (ports) + entry-point plugin per project, delivered as a pytest plugin**.

## Architecture (monorepo, separately installable packages)

**`testbed-core/` — pytest plugin (`pytest11` entry point)**
- `ports.py` — abstract ports (ABC/Protocol): `ProjectAdapter` (setup/health_check/client/teardown/describe), `ReportSink`, `Environment`. Tests depend on ports only (dependency inversion).
- `discovery.py` — loads project plugins via `importlib.metadata.entry_points(group="testbed.projects")`; builds the registry (name -> adapter factory; projects that need their own fixtures ship them through their own `pytest11` entry point (revisit in Phase 3)). Core never imports a project.
- `fixtures.py` — composition root, layered by scope: session (`env_config`, `aws_session`, `report_sink`), module (`adapter` resolved by project name from marker/ini), function (`client`, `artifact_dir`).
- `reporting/` — `RunReport` dataclass built from pytest hooks (`pytest_runtest_logreport`, `pytest_sessionfinish`); sinks: `JsonSink`, `NotionSink`.
- `retry.py` — rerun-once flaky detection; flaky tests are tagged in the report, never silently passed.
- Test doubles in core: `FakeAdapter` so the framework is testable offline.

**Project plugins (each its own package, registers via entry point, ships its adapter + tests)**
- `projects/jobfetcher/` — `JobFetcherAdapter` (invokes deployed Lambda via boto3, reads S3 output) + contract tests: output schema, freshness, dedupe, one-source-failing tolerance.
- `projects/publicapi/` — adapter for a free public REST API + contract/latency tests. Proves "add a project without touching core".

**`services/jobfetcher/` — Lambda under test**
- `JobSource` ABC strategies: Greenhouse board API, Lever postings API (company list in config). Normalize to `JobPost` dataclass; write `jobs/<date>.json` to S3.
- `template.yaml` (SAM): Lambda, EventBridge daily schedule, S3 bucket, least-privilege IAM, GitHub OIDC role.

**CI (`.github/workflows/`)**
- `test.yml` (push/PR/schedule): build Docker test image, `pytest -n auto` in container, upload report artifact, `NotionSink` creates a row in the "Test Runs" DB plus a report page (per-project results, flaky list, sample jobs, run URL, commit SHA); link printed in the job summary.
- `deploy.yml`: `sam build && sam deploy` via OIDC (no long-lived keys).
- Secrets: `NOTION_TOKEN` (internal integration), `NOTION_DB_ID`, AWS role ARN.

## Phases (each on its own branch, merged `--no-ff`, never deleted — phase-branch-workflow)
1. **Core** — ports, discovery, fixtures, JsonSink, FakeAdapter; offline unit tests.
2. **Job-fetcher Lambda + SAM** — sources, normalization, `sam local invoke`, deploy.
3. **Project plugins + Docker** — jobfetcher and publicapi packages; parallel run in container.
4. **CI + Notion** — workflows, NotionSink, shareable link.
5. **Polish** — README written as internal docs, architecture diagram, "add a new project in 5 steps" guide, interview talking points.

## Verification
- P1: core tests pass using `FakeAdapter`; `pytest --trace-config` shows the plugin loaded; entry-point discovery test.
- P2: `sam local invoke` returns normalized jobs; deployed Lambda writes to S3.
- P3: `docker run testbed pytest -n auto` green; both projects discovered via entry points.
- P4: a push triggers the workflow; new Notion row and page appear; link in job summary.
- Lean verification: targeted tests plus build per milestone.

## Open items for implementation time
- Which company boards to poll (config file, not hardcoded).
- AWS account/region; Notion workspace and database creation.
- No remote push without explicit per-instance approval.
