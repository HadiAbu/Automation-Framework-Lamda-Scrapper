# testbed

A small multi-project test-automation platform: a pytest plugin with a hexagonal core, where each project under test ships its own adapter as an entry-point plugin. Built as a portfolio piece for an automation-infrastructure role.

> **Status:** Phase 1 (core framework) complete; later phases pending.

## Idea

- **Core** defines ports (`ProjectAdapter`, `ReportSink`, `Environment`) and the pytest fixtures that wire them together. Tests depend on ports, never on project internals.
- **Projects** register through the `testbed.projects` entry point. Adding one means adding a package, with no core changes.
- **Projects under test:**
  - `jobfetcher`: an AWS Lambda that fetches job posts from public Greenhouse/Lever board APIs on a daily schedule and writes them to S3.
  - `publicapi`: a second, small target that proves the platform is reusable.
- **CI:** GitHub Actions runs the suite in Docker and publishes each run to a Notion database, with a shareable report link.

## Stack

Python 3.13, pytest (+ xdist), AWS SAM (Lambda, EventBridge, S3), Docker, GitHub Actions, Notion API.

## Roadmap

1. Core framework (ports, discovery, fixtures, JSON reporting)
2. Job-fetcher Lambda + SAM
3. Project plugins + Docker
4. CI + Notion reporting
5. Docs and polish

Each phase is developed on its own branch and merged into `main`.
