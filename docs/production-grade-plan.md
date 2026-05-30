# Path to A+ — Phase-by-Phase Production Plan

A staged plan to take the finance platform (`fin-front` · `fin-mobile` · `fin-backend` + Postgres) from clean prototype to top-tier (A+/O) on every dimension. Phases are ordered by risk: correctness and security first, then contract/scale, then observability, then platform maturity.

> **Operating principle:** No phase is "done" until its exit criteria are green and enforced in CI. Each phase only raises grades that its workstreams actually verify — the final column of every dimension lands at A+/O, with the acceptance bar defined at the bottom.

## Snapshot

| Metric | Value |
|---|---|
| Phases | 5 (P0–P4) |
| To full A+ (1–2 eng) | ~16 weeks |
| Dimensions → A+/O | 12 |
| P0/P1 ship-blockers | 9 |

## Dimension grade trajectory

| Dimension | Now | Reaches A-grade in | Target |
|---|:---:|:---:|:---:|
| Code structure / layering | A- | P4 | A+ |
| Data modeling | B+ | P1 (audit + soft delete) | A+ |
| Data integrity / concurrency | C | P1 (locks + idempotency) | A+ |
| Auth (mechanism) | B- | P2 (tokens + Redis) | A+ |
| Security hardening | C- | P1 (CSRF / rate-limit / headers) | A+ |
| API contract / typing | C+ | P2 (generated clients) | A+ |
| Automated testing | D | P3 (E2E + load) | A+ |
| CI / CD | F | P0 → A by P3 | A+ |
| Observability | D | P3 (OTel + metrics + SLOs) | A+ |
| Scalability / infra | C | P2 → A by P4 | A+ |
| Mobile auth fit | C | P2 (token auth) | A+ |
| Compliance / privacy / governance | D | P4 | A+ |

---

## P0 — Foundations & guardrails (Week 0–1)
Make the repo safe to change fast: a working pipeline, test harness, secrets discipline, and governance — before touching money logic.

| Workstream | Tasks · exit criteria |
|---|---|
| CI skeleton | GitHub Actions: lint + typecheck (web, mobile, backend) + docker build on every PR. Branch protection requires green. **Exit: red PRs cannot merge.** |
| Test harness | pytest + httpx async client + throwaway Postgres (testcontainers) for backend; Vitest/RTL for web. **Exit: one real test runs in CI per app.** |
| Secrets & config | Pydantic settings validate at boot — fail if `SECRET_KEY` is default or <32 chars; per-env config; `.env` never committed. **Exit: app refuses to start insecure.** |
| Supply chain | Dependabot, secret scanning, SAST (CodeQL/bandit/eslint-security). **Exit: scans run on PR.** |
| Repo hygiene | Decide on the ~85 `glossary_slices/term_*.py` + ~85 FE filler files (remove or document); add ADRs + CODEOWNERS + pre-commit. **Exit: tree reflects real surface.** |

## P1 — Correctness & security hardening (Week 1–4)
**Highest-risk phase — money + auth.** Until this ships, the platform must not hold real money or real users.

| Workstream | Tasks · exit criteria |
|---|---|
| Concurrency-safe ledger | Lock the account row (`SELECT … FOR UPDATE`) before balance mutation in `TransactionService`, or move balance to a derived/materialized sum. One transaction per create/update/delete. **Exit: concurrent-write test shows no drift.** |
| Idempotency | `Idempotency-Key` header on transaction create, stored + replayed. **Exit: duplicate POST returns the original, writes once.** |
| Audit & soft delete | Append-only audit log for financial mutations; soft-delete instead of cascade hard-delete. **Exit: every money change is reconstructable.** |
| Auth hardening | CSRF tokens for cookie mutations, login rate-limit + lockout, cookie `Secure` + tightened `SameSite`, scoped CORS (no `*` with credentials). **Exit: OWASP auth checks pass.** |
| Edge security headers | nginx: CSP, HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy. **Exit: securityheaders.io A.** |
| Migrations as a job | Remove `alembic upgrade` from `init_db()`; run as a release/CI step. **Exit: replicas boot without migrating.** |
| Kill demo-auth in prod | Gate `liveAuthCoordinator` localStorage fallback behind a dev flag. **Exit: 5xx never appears authenticated.** |
| Error envelope | Global exception handler emits one RFC-7807 shape the FE parser already expects. **Exit: all errors share a schema.** |

## P2 — Contract, scale & resilience (Week 4–8)

| Workstream | Tasks · exit criteria |
|---|---|
| Typed API contract | Generate web + mobile clients from the FastAPI OpenAPI schema; delete hand-duplicated types. **Exit: client drift fails CI (regenerate + diff).** |
| Pagination | Cursor/limit pagination on every list endpoint (`list_for_user` et al.). **Exit: no unbounded responses.** |
| Redis | Revocable server-side sessions, rate-limit buckets, cache layer. **Exit: force-logout works; hot reads cached.** |
| Mobile token auth | Access + refresh tokens (or robust session store) for `fin-mobile` instead of fragile RN cookies. **Exit: session survives app restart + refresh rotates.** |
| Background worker | arq/Celery for email, statement imports, AI jobs. **Exit: long work runs off the request path.** |
| DB & lifecycle | Pool tuning, query-driven indexes, real readiness probe (DB check), graceful shutdown, automated backups + restore test. **Exit: restore drill passes.** |

## P3 — Observability & quality (Week 8–11)

| Workstream | Tasks · exit criteria |
|---|---|
| Logs + errors | Structured JSON logs propagating the `X-Request-Id` the FE already sends; Sentry on web, mobile, backend. **Exit: any error is traceable end-to-end.** |
| Tracing + metrics | OpenTelemetry traces + Prometheus/Grafana dashboards (latency, error rate, DB). **Exit: golden-signal dashboards live.** |
| SLOs & alerts | Define SLOs (availability, p95 latency) with alerting + on-call routing. **Exit: breaches page someone.** |
| Test depth | Service/repo/auth unit + integration coverage gate; Playwright (web) + Maestro/Detox (mobile) over money flows; k6 load test. **Exit: coverage threshold enforced in CI.** |

## P4 — Platform maturity & top-tier (Week 11–16)

| Workstream | Tasks · exit criteria |
|---|---|
| Infra as code + deploys | Terraform; managed Postgres; ECS/K8s; blue-green/canary with auto-rollback; multi-env promotion. **Exit: zero-downtime deploys, reproducible infra.** |
| AuthZ & admin plane | Roles/permissions beyond owner-only; separated admin surface. **Exit: least-privilege enforced.** |
| Data resilience | PITR backups, read replicas as needed, verified encryption in transit + at rest, DR drill. **Exit: RPO/RTO targets met in a drill.** |
| Compliance & privacy | Data-handling review (PCI-adjacent), data-subject export/delete, retention policy, WAF, feature flags. **Exit: privacy + security review signed off.** |
| Governance | Contract tests, SBOM, runbooks, ADR catalog kept current. **Exit: a new engineer can operate it from docs.** |

---

## Definition of A+ (acceptance bar per dimension)

| Dimension | What A+/O means here |
|---|---|
| Data integrity / concurrency | No balance drift under concurrent load; every mutation idempotent + audited. |
| Security hardening | CSRF + rate-limit + secure cookies + headers + WAF; clean SAST/secret scans. |
| Auth | Revocable sessions/tokens, refresh rotation, RBAC, MFA-ready. |
| API contract / typing | Single source of truth; generated clients; drift fails CI. |
| Testing | Unit + integration + E2E + load, with enforced coverage gates. |
| CI / CD | Every change linted, typed, tested, scanned, deployed via canary with rollback. |
| Observability | Logs + traces + metrics correlated by request id; SLOs with alerting. |
| Scalability / infra | IaC, orchestration, horizontal scale, Redis + worker, restore-tested backups. |
| Mobile | Token auth that survives restarts; parity with web on shared API. |
| Compliance / governance | Data export/delete, retention, DR drill, runbooks, ADRs current. |
