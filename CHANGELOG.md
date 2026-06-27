# Changelog

All notable changes to this project are documented here. The format is based on
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project aims
to follow [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Structured JSON logging (`app/observability`) with per-request access logging
  (method, path, status, latency, request id) and a configurable `LOG_LEVEL`.
- Backend test suite covering goal-planning math, login throttling, request-id
  and CSRF middleware, structured logging, app wiring, and schema validation.
- DB-backed integration tests (`tests/integration`) that verify account-balance
  consistency across create/update/delete, idempotent replays, soft-delete
  reversal, and concurrent writes to the same account (proving the
  `SELECT ... FOR UPDATE` row lock prevents lost updates). The CI backend job
  now runs against a Postgres service with migrations applied.
- Coverage reporting via `pytest-cov` with a CI coverage floor (65%) and an
  uploaded coverage artifact.
- Integration tests for the budget, goal, and auth flows against Postgres.
- Prometheus metrics middleware and `/metrics` endpoint (request counters,
  latency histogram, in-progress gauge), plus opt-in OpenTelemetry tracing
  enabled via `OTEL_EXPORTER_OTLP_ENDPOINT`.
- Security response headers (CSP, HSTS, X-Frame-Options, X-Content-Type-Options,
  Referrer-Policy, Permissions-Policy, COOP) via middleware and nginx.
- Distributed-ready login throttling: pluggable in-memory (default) or Redis
  backend selected by `REDIS_URL`.
- Security workflow: gitleaks secret scanning, Trivy vulnerability scan (SARIF
  to code scanning), and SPDX SBOM generation.
- Release workflow: tag-driven publishing of API and web images to GHCR with
  provenance + SBOM, and a GitHub release with generated notes.
- Typed API contract: `scripts/export_openapi.py` plus `openapi-typescript`
  generation (`npm run gen:api-types`); CI fails if the committed schema drifts.
- Repository governance: root `README`, `CONTRIBUTING`, `SECURITY` policy,
  `CHANGELOG`, Apache-2.0 `LICENSE`, `CODEOWNERS`, and issue/PR templates.
- Operations runbooks (`docs/runbooks.md`) and a branch-protection setup guide
  (`docs/branch-protection.md`).

### Changed
- CI and CodeQL workflows now run automatically on push and pull requests to
  `main` (previously manual `workflow_dispatch` only); CodeQL also runs weekly.

### Fixed
- Resolved a circular import between `app.auth.wiring` and `app.api.v1.auth`
  that prevented the full application (`app.main`) from importing. CSRF token
  generation moved to `app.auth.csrf_token`; a regression test now guards it.
- Account, budget, and goal deletes called `AsyncSession.delete()` without
  awaiting it, so the delete silently no-opped and the row was never removed.
  The repository `delete` methods are now async and awaited; integration tests
  cover each.

## [0.1.0] - prior work
- Initial monorepo: FastAPI modular-monolith API, React/Vite web app, and Expo
  mobile shell, with Docker Compose, Alembic migrations, CSRF protection, login
  throttling, idempotency keys, and an audit-event model.
