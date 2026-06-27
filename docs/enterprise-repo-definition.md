# Enterprise-Grade Repository: Definition & Scorecard

This document defines what "enterprise-grade" means for this repository and
tracks where `finance-tracker` stands against that bar. It is a living rubric —
update the scorecard as the project matures.

## What "enterprise-grade" means

An enterprise-grade repository is one a large organization can run reliably in
production, with many contributors and a low tolerance for outages. It is judged
less by *what the app does* and more by the engineering discipline *around* the
code. The dimensions:

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

Grades: **A** (enterprise-grade) → **F** (absent). Last reviewed against the
`enterprise-repo-definition` work.

| Dimension | Grade | Evidence |
|---|:---:|---|
| Structure & ownership | A- | Modular monolith (`app/modules/*`), real `CODEOWNERS`, architecture review + ADRs |
| Automated quality gates | B+ | CI runs web/mobile/api + Docker build on push/PR; coverage floor enforced. **Branch protection must be enabled in repo settings.** |
| Security & compliance | B | CodeQL (weekly + PR), Dependabot, `SECURITY.md`, secret-strength enforcement, CSRF + login throttling |
| Documentation & onboarding | A- | Root `README`, `CONTRIBUTING`, per-app docs, ADRs, phased roadmap |
| Reproducible builds | A- | Dockerfiles + Compose, `poetry.lock`/`package-lock.json`, Alembic migrations |
| Observability & operability | B | JSON structured logging, per-request access logs with latency + request id, `/health/live` + `/health/ready`. Metrics/tracing still TODO. |
| Governance & process | A- | Apache-2.0 `LICENSE`, `CHANGELOG`, issue/PR templates, `CODEOWNERS` |

## Remaining gaps (not fixable in-repo alone)

These require repository **settings** or longer-horizon work:

1. **Branch protection** — require passing CI + ≥1 Code Owner review on `main`,
   disallow direct pushes. (GitHub repo settings.)
2. **DB-backed integration tests** — services/repositories are exercised only
   indirectly today; add a Postgres service to CI and raise the coverage floor.
3. **Metrics & tracing** — structured logs are in place; Prometheus metrics and
   distributed tracing remain on the roadmap (`docs/phases/phase-3-*`).
4. **Concurrency hardening** — see the balance-race item in the architecture
   review; row-level locking / optimistic concurrency for account balances.

## How to raise a grade

When you close a gap, update the relevant row's grade and evidence here and add
an entry to [`CHANGELOG.md`](../CHANGELOG.md). The scorecard should always
reflect the repository's real state, not its aspirations.
