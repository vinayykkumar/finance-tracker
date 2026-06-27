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
- Coverage reporting via `pytest-cov` with a CI coverage floor and an uploaded
  coverage artifact.
- Repository governance: root `README`, `CONTRIBUTING`, `SECURITY` policy,
  `CHANGELOG`, Apache-2.0 `LICENSE`, `CODEOWNERS`, and issue/PR templates.

### Changed
- CI and CodeQL workflows now run automatically on push and pull requests to
  `main` (previously manual `workflow_dispatch` only); CodeQL also runs weekly.

### Fixed
- Resolved a circular import between `app.auth.wiring` and `app.api.v1.auth`
  that prevented the full application (`app.main`) from importing. CSRF token
  generation moved to `app.auth.csrf_token`; a regression test now guards it.

## [0.1.0] - prior work
- Initial monorepo: FastAPI modular-monolith API, React/Vite web app, and Expo
  mobile shell, with Docker Compose, Alembic migrations, CSRF protection, login
  throttling, idempotency keys, and an audit-event model.
