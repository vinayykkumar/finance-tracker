# P1 — Correctness & Security Hardening

**Duration:** Week 1–4
**Goal:** Close the ledger race and the cookie-auth exposure. This is the highest-risk phase.

> **Ship-blocker:** Until this phase ships, the platform must not hold real money or real users.

> Related: [`../architecture-review.md`](../architecture-review.md) · [`../production-grade-plan.md`](../production-grade-plan.md)

## Why this phase
Two P0-severity issues live here: account balances can corrupt under concurrency, and cookie auth has no CSRF / rate-limiting / secure cookies. Both must be fixed before real usage.

## Workstreams

| Workstream | Tasks | Exit criteria |
|---|---|---|
| Concurrency-safe ledger | In `TransactionService`, lock the account row (`SELECT … FOR UPDATE`) before balance mutation, or move balance to a derived/materialized sum. Wrap create/update/delete in a single transaction. | Concurrent-write test shows no balance drift. |
| Idempotency | `Idempotency-Key` header on transaction create; store the key + result and replay on repeat. | Duplicate POST returns the original and writes only once. |
| Audit & soft delete | Append-only audit log for financial mutations; soft-delete instead of cascade hard-delete. | Every money change is reconstructable from history. |
| Auth hardening | CSRF tokens for cookie mutations; login rate-limit + lockout; cookie `Secure` + tightened `SameSite`; scoped CORS (no `*` with credentials). | OWASP auth checklist passes. |
| Edge security headers | nginx: CSP, HSTS, X-Frame-Options, X-Content-Type-Options, Referrer-Policy. | securityheaders.io grade A. |
| Migrations as a job | Remove `alembic upgrade head` from `init_db()`; run it as a dedicated release/CI step. | Replicas boot without migrating. |
| Kill demo-auth in prod | Gate the `liveAuthCoordinator` localStorage fallback behind a dev-only flag. | A 5xx never makes the UI appear authenticated. |
| Error envelope | Global exception handler emits one RFC-7807 shape the frontend parser already expects. | All API errors share a single schema. |

## Prerequisites
- **P0** complete (CI + tests + secure config), so these changes are verifiable.

## Dimensions advanced
- **Data integrity / concurrency:** C → A- (locks + idempotency + audit)
- **Security hardening:** C- → A- (CSRF / rate-limit / headers / secure cookies)
- **Data modeling:** B+ → A- (audit log + soft delete)
- **API contract / typing:** C+ → B (consistent error envelope)
- **Scalability / infra:** C → C+ (migrations decoupled from boot)

## Phase completion checklist
- [ ] Concurrent-write load test shows zero balance drift
- [ ] Transaction create is idempotent via `Idempotency-Key`
- [ ] Financial mutations are audited; deletes are soft
- [ ] CSRF + login rate-limit/lockout + `Secure` cookies + scoped CORS in place
- [ ] Security headers return grade A
- [ ] Migrations run as a release step, not on app boot
- [ ] Demo-auth fallback disabled outside dev
- [ ] All errors return one RFC-7807 schema
