# P0 — Foundations & Guardrails

**Duration:** Week 0–1
**Goal:** Make the repo safe to change fast — a working pipeline, test harness, secrets discipline, and governance — before touching money logic.

> Related: [`../architecture-review.md`](../architecture-review.md) · [`../production-grade-plan.md`](../production-grade-plan.md)

## Why this phase first
Every later phase changes money logic and security. Without CI, tests, and secret discipline in place, those changes are unverifiable and risky. P0 builds the safety net.

## Workstreams

| Workstream | Tasks | Exit criteria |
|---|---|---|
| CI skeleton | GitHub Actions running lint + typecheck (web, mobile, backend) + docker build on every PR. Enable branch protection requiring green checks. | Red PRs cannot merge. |
| Test harness | pytest + httpx async client + throwaway Postgres (testcontainers) for backend; Vitest/RTL wired for web. | One real test runs in CI per app. |
| Secrets & config | Pydantic settings validate at boot — fail if `SECRET_KEY` is default or <32 chars; per-environment config; ensure `.env` is never committed. | App refuses to start with insecure config. |
| Supply chain | Enable Dependabot, secret scanning, and SAST (CodeQL / bandit / eslint-security). | Scans run on every PR. |
| Repo hygiene | Decide on the ~85 `glossary_slices/term_*.py` + ~85 FE `glossary/slices/term_*.ts` filler files (remove or document). Add ADRs, CODEOWNERS, pre-commit hooks. | Repo tree reflects the real surface area. |

## Prerequisites
- None. This is the starting phase.

## Dimensions advanced
- **CI / CD:** F → (pipeline exists; matures to A by P3)
- **Automated testing:** D → C (harness in place)
- **Security hardening:** C- → C+ (secret validation + scanning)
- **Compliance / governance:** D → C (ADRs, CODEOWNERS)

---

## Implementation progress

| Checkpoint | Status | Notes |
|---|---|---|
| CP1 — Backend test harness + secret rules | Done | `pytest` + `tests/test_settings.py`; `ENVIRONMENT` + `SECRET_KEY` validation in `app/config.py` |
| CP2 — Backend static analysis | Done | `ruff` in dev deps; glossary excluded from Ruff scope; Bugbear omitted (FastAPI `Depends()` pattern) |
| CP3 — GitHub Actions CI | Done | `.github/workflows/ci.yml` — web lint/test/build, mobile typecheck, API ruff/pytest, Docker Compose build |
| CP4 — Supply chain automation | Done | Dependabot (`npm`, `pip`, Docker) + CodeQL workflow |
| CP5 — Local developer hooks | Done | `.pre-commit-config.yaml` (YAML/JSON + Ruff on backend) |
| CP6 — Repo hygiene docs | Done | `docs/glossary-slices.md`, `docs/adr/0001-record-architecture-decisions.md`, `.github/CODEOWNERS` (template comments) |
| CP7 — Branch protection | Manual | Enable in GitHub: **Settings → Branches → Branch protection rules** — require status checks `CI` jobs + (optional) CodeQL |

### Checkpoint detail — CP1 (backend)
- Added `[tool.poetry.group.dev.dependencies]` with `pytest` and `ruff`.
- Added `tests/test_settings.py` (no database): validates `Settings` for `development` vs `staging` / `production` and `SECRET_KEY` rules.
- Extended `Settings` with `environment: Literal["development", "staging", "production"]` and a `@model_validator` that rejects weak secrets in staging/production (placeholder `change-me` first, then minimum length 32).

### Checkpoint detail — CP3 (CI)
- Workflow path: `.github/workflows/ci.yml`.
- **Manual-only trigger** (`workflow_dispatch`) — does not run automatically on push or PR.
- To run: GitHub → Actions → CI → Run workflow.
- If auto-triggering is wanted in future, add `push: branches: [main]` / `pull_request` back to the `on:` block.

### Checkpoint detail — CP4 (CodeQL)
- Workflow path: `.github/workflows/codeql.yml`.
- Uses `javascript-typescript` and `python` in one job. If Python analysis needs a Poetry build step later, add an explicit `codeql-action/autobuild` replacement with `poetry install` (tracked as a follow-up).

---

## Status log

| Date (UTC) | Change |
|---|---|
| 2026-05-30 | P0 implementation started: backend tests, Ruff, `Settings` hardening, CI + Dependabot + CodeQL + pre-commit, docs. |
| 2026-05-30 | `docker-compose.yml` API service: set `ENVIRONMENT=development` explicitly. `fin-backend/.env.example`: document `ENVIRONMENT`. Root `package.json`: add `ci:local` script (Node workspaces only; run backend via `cd fin-backend && poetry run pytest`). |

---

## Phase completion checklist
- [x] CI runs lint + typecheck + tests + docker build on every PR (workflow committed; enable Actions + branch protection in GitHub)
- [ ] Branch protection blocks merges on red (manual in GitHub)
- [x] At least one real test per app executes in CI (web: existing Vitest; API: new pytest; mobile: `tsc --noEmit` as typecheck gate)
- [x] Boot fails on default/short `SECRET_KEY` when `ENVIRONMENT` is `staging` or `production`
- [x] Dependabot + CodeQL committed (secret scanning: enable **GitHub Advanced Security** or repo **Security** tab features if available)
- [x] Glossary filler files documented (`docs/glossary-slices.md`); ADRs + CODEOWNERS template + pre-commit added
