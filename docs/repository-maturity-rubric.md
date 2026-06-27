# Repository Maturity Rubric & Scorecard

This document defines what "production-grade" means for this repository and
tracks where `finance-tracker` stands against that bar. It is a living rubric —
update the scorecard as the project matures.

## What "production-grade" means

A production-grade repository is one a team can run reliably in production, with
many contributors and a low tolerance for outages. It is judged less by *what
the app does* and more by the engineering discipline *around* the code. The
dimensions:

| # | Dimension | What it requires |
|---|---|---|
| 1 | **Structure & ownership** | Clear module boundaries; `CODEOWNERS`; documented architecture |
| 2 | **Automated quality gates** | Lint, tests, type-checks, and builds run on every PR; branch protection |
| 3 | **Security & compliance** | SAST, dependency scanning, secret hygiene, vulnerability disclosure |
| 4 | **Documentation & onboarding** | README, contributing guide, ADRs; a newcomer can build and run from docs |
| 5 | **Reproducible builds** | Containerization, pinned lockfiles, versioned DB migrations |
| 6 | **Observability & operability** | Structured logs, health checks, request correlation, metrics |
| 7 | **Governance & process** | Versioning, changelog, license, issue/PR templates |

## Scorecard

Grades: **A** (production-grade) → **F** (absent). Last reviewed against the
repository-hardening work.

| Dimension | Grade | Evidence |
|---|:---:|---|
| Structure & ownership | A | Modular monolith (`app/modules/*`), real `CODEOWNERS`, architecture review + ADRs, typed API contract shared with clients |
| Automated quality gates | A | CI runs web/mobile/api (against a Postgres service) + Docker build + Playwright E2E (manual `workflow_dispatch`); backend coverage floor (65%); web unit/component tests + coverage; working ESLint gate; DB-backed integration + concurrency tests; OpenAPI drift check. **Branch protection must still be toggled in repo settings — see [branch-protection.md](./branch-protection.md).** |
| Security & compliance | A- | CodeQL, Dependabot, gitleaks secret scan, Trivy vuln scan (SARIF), SBOM; secret-strength enforcement; CSRF, login throttling, security headers (CSP/HSTS/etc.); role-based access control (`require_admin`) on the admin/audit surface, additive to per-user ownership scoping |
| Documentation & onboarding | A | Root `README`, `CONTRIBUTING`, `SECURITY`, runbooks, per-app docs, ADRs, phased roadmap, Kubernetes deploy runbook (`deploy/README.md`) |
| Reproducible builds | A | Multi-stage non-root Dockerfiles + Compose, Helm chart for Kubernetes (`deploy/helm/finance-tracker`, with a pre-upgrade migration Job), `poetry.lock`/`package-lock.json`, Alembic migrations, tag-driven GHCR releases with provenance + SBOM |
| Observability & operability | A- | JSON structured logging, access logs (latency + request id), Prometheus `/metrics`, opt-in OpenTelemetry tracing, `/health/live` + `/health/ready`, runbooks |
| Governance & process | A | Apache-2.0 `LICENSE`, `CHANGELOG`, issue/PR templates, `CODEOWNERS`, release automation |

## The one remaining gap

**Branch protection** is the only item that cannot be closed from inside the
repository — it is a GitHub **repo setting**. Every gate above is built and
green, but until protection is enabled they are advisory. Turn it on (require
CI + CodeQL to pass, require ≥1 Code Owner review, block direct pushes) using
the click-path or `gh` script in [branch-protection.md](./branch-protection.md).
Once enabled, this repository meets the production-grade bar across every
dimension.

## Resolved

- **Concurrency hardening** — account-balance updates use `SELECT ... FOR UPDATE`
  row locks; a concurrency integration test asserts no lost updates (fails if
  the lock is removed).
- **DB-backed integration tests** — `tests/integration` exercises transactions,
  budgets, goals, and auth against Postgres; CI provisions a Postgres service.
- **Async delete bug** — account/budget/goal repositories awaited
  `AsyncSession.delete()` (previously a silent no-op); caught by integration tests.
- **Metrics & tracing** — Prometheus `/metrics` and opt-in OTLP tracing shipped.
- **Security hardening** — security-headers middleware + nginx headers; gitleaks,
  Trivy, and SBOM in CI.
- **Distributed rate limiting** — login throttle now has a Redis backend for
  multi-replica deployments.
- **Typed API contract** — clients generate types from the server's OpenAPI
  schema; CI fails on drift.
- **Role-based access control** — `role` column + `require_role`/`require_admin`
  gate an admin/audit surface, additive to per-user ownership scoping.
- **Frontend & E2E tests** — Vitest + Testing Library unit/component tests with
  coverage, and Playwright E2E against the Compose stack in CI.
- **Working lint gate** — added the missing ESLint config so `npm run lint`
  actually runs (it previously errored with "no configuration found").
- **Kubernetes packaging** — a Helm chart (probes, HPA, PDBs, Ingress, migration
  Job, opt-in NetworkPolicy, non-root) plus a deploy runbook.
- **Container hardening** — multi-stage backend image running as a non-root user
  with a `HEALTHCHECK`.
- **Repo hygiene** — removed ~170 unused glossary-filler modules and the
  redundant `main_auth.py` / `main_minimal.py` entrypoints.

## How to raise a grade

When you close a gap, update the relevant row's grade and evidence here and add
an entry to [`CHANGELOG.md`](../CHANGELOG.md). The scorecard should always
reflect the repository's real state, not its aspirations.
