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

## Phase 2 detail: job-fetcher Lambda + SAM (decided 2026-10-07)

**Scope:** build `services/jobfetcher/` with TDD offline, validate locally with SAM, then perform a real deploy to AWS region **eu-north-1**. The GitHub OIDC role from the template sketch above moves to Phase 4 (CI); Phase 2 deploys from the developer's machine.

**Approach:** one Lambda that loops over the configured boards. Each source runs in isolation (own `try/except` and timeout); a failing source is recorded in the output and does not fail the run. The run fails only if every source failed. (Rejected: per-source fan-out with Step Functions/SQS as over-engineered; fail-fast as one flaky board would lose the day's data.)

**Layout (`services/jobfetcher/`):** `src/jobfetcher/{models,config,pipeline,storage,handler}.py`, `src/jobfetcher/sources/{base,greenhouse,lever}.py`, `template.yaml`, `src/jobfetcher/boards.json (ships inside the Lambda zip)`, `tests/`. No third-party runtime dependencies: stdlib `urllib` for HTTP and the Lambda-provided `boto3` for S3. No Lambda layer.

**Sources (public, unauthenticated, verified live 2026-10-07):**
- Greenhouse: `GET https://boards-api.greenhouse.io/v1/boards/<token>/jobs?content=true`
- Lever: `GET https://api.lever.co/v0/postings/<company>?mode=json`
- Default boards (config, not code): Greenhouse `stripe`, `figma`, `cloudflare`; Lever `spotify`, `palantir`.

**Data model:** `JobPost(id, source, company, title, location, url, posted_at, description, matched_keywords)`. Jobs are deduplicated by `(source, id)`. All jobs are kept; `matched_keywords` is computed from title + description against a configurable keyword list (default: `automation`, `sdet`, `qa`, `test`, `infrastructure`, `python`).

**Output (S3):** two objects per run, `jobs/<YYYY-MM-DD>.json` and `jobs/latest.json`:
```json
{"generated_at": "ISO-8601",
 "sources": [{"name": "greenhouse:stripe", "ok": true, "count": 123, "error": null}],
 "jobs": [{"id": "", "source": "", "company": "", "title": "", "location": "", "url": "",
           "posted_at": "", "description": "", "matched_keywords": []}]}
```
The `sources` block is what the Phase 3 contract tests assert on (schema, freshness, dedupe, one-source-failing tolerance).

**SAM template:** Python 3.13, x86_64, 512 MB, 120 s timeout (five boards return ~21 MB of JSON and take ~18 s sequentially, measured 2026-10-07); one S3 bucket (SSE on, public access blocked, 30-day lifecycle on dated objects); daily EventBridge schedule; least-privilege role (`s3:PutObject` on `jobs/*` only) plus CloudWatch logs.

**Testing:** TDD with the HTTP fetcher and the S3 client injected, using recorded Greenhouse/Lever fixtures, all offline. Verification: unit tests green, `sam validate`, `sam local invoke` (Docker), then `sam deploy`, an invoke, and a check that `jobs/latest.json` exists and parses. A `{"dry_run": true}` event runs fetch + normalize + tag and returns the summary without touching S3, so `sam local invoke` needs no AWS credentials.

**AWS setup (user-run, credentials never shared with the assistant):** install AWS CLI and SAM CLI; configure credentials locally (`aws configure sso` or `aws configure`); deploy with a dedicated non-root IAM user (the Lambda's runtime role is least-privilege; narrowing the deployer is a Phase 4 item).
