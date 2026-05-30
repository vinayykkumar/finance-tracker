# P2 — Contract, Scale & Resilience

**Duration:** Week 4–8
**Goal:** Eliminate API drift, add horizontal-scale primitives, and make the system resilient.

> Related: [`../architecture-review.md`](../architecture-review.md) · [`../production-grade-plan.md`](../production-grade-plan.md)

## Why this phase
With correctness and security handled, the next risks are: hand-duplicated API types drifting between web and mobile, unbounded list responses, fragile mobile cookie auth, and a single-process design with no caching, jobs, or tested backups.

## Workstreams

| Workstream | Tasks | Exit criteria |
|---|---|---|
| Typed API contract | Generate web + mobile clients from the FastAPI OpenAPI schema; delete hand-duplicated types. | Client drift fails CI (regenerate + diff check). |
| Pagination | Add cursor/limit pagination to every list endpoint (`list_for_user` et al.). | No unbounded responses. |
| Redis | Revocable server-side sessions, rate-limit buckets, and a cache layer. | Force-logout works; hot reads are cached. |
| Mobile token auth | Access + refresh tokens (or a robust session store) for `fin-mobile` instead of fragile RN cookies. | Session survives app restart; refresh rotates. |
| Background worker | arq/Celery worker for email, statement imports, and AI jobs. | Long work runs off the request path. |
| DB & lifecycle | Connection-pool tuning, query-driven indexes, real readiness probe (DB check), graceful shutdown, automated backups + restore test. | Restore drill passes. |

## Prerequisites
- **P1** complete (secure, correct, single error schema), so generated clients and pagination build on a stable contract.

## Dimensions advanced
- **API contract / typing:** B → A (generated clients, drift-proof)
- **Auth (mechanism):** B- → A (Redis-backed revocable sessions / tokens)
- **Mobile auth fit:** C → A (token auth that survives restarts)
- **Scalability / infra:** C+ → A- (Redis + worker + DB tuning + backups)

## Phase completion checklist
- [ ] Web + mobile API clients are generated from OpenAPI; manual types deleted
- [ ] CI fails when generated clients drift from the schema
- [ ] All list endpoints paginate
- [ ] Redis powers revocable sessions, rate limits, and caching
- [ ] Mobile uses access/refresh tokens; session survives restart
- [ ] Background worker handles async jobs
- [ ] Readiness probe checks the DB; graceful shutdown works
- [ ] Automated backups exist and a restore drill passes
