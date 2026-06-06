# P3 — Observability & Quality

**Duration:** Week 8–11
**Goal:** Make the system measurable and provably correct — logs, traces, metrics, SLOs, and a full test pyramid.

> Related: [`../architecture-review.md`](../architecture-review.md) · [`../production-grade-plan.md`](../production-grade-plan.md)

## Why this phase
Once the system is correct and scalable, you must be able to *see* it in production and *prove* it stays correct. This phase adds end-to-end traceability and enforced test depth.

## Workstreams

| Workstream | Tasks | Exit criteria |
|---|---|---|
| Logs + errors | Structured JSON logs propagating the `X-Request-Id` the frontend already sends; Sentry on web, mobile, and backend. | Any error is traceable end-to-end by request id. |
| Tracing + metrics | OpenTelemetry traces + Prometheus/Grafana dashboards (latency, error rate, DB). | Golden-signal dashboards are live. |
| SLOs & alerts | Define SLOs (availability, p95 latency) with alerting + on-call routing. | SLO breaches page someone. |
| Test depth | Service/repo/auth unit + integration coverage gate; Playwright (web) + Maestro/Detox (mobile) over money flows; k6 load test. | Coverage threshold enforced in CI. |

## Prerequisites
- **P2** complete (stable contract + scalable infra), so tracing/metrics span the real architecture and E2E tests cover token auth + pagination.

## Dimensions advanced
- **Observability:** D → A (logs + traces + metrics + SLOs correlated by request id)
- **Automated testing:** C → A (unit + integration + E2E + load with coverage gates)
- **CI / CD:** B+ → A (coverage + E2E gates in the pipeline)

## Phase completion checklist
- [ ] Structured logs carry the request id end-to-end
- [ ] Sentry captures errors on web, mobile, and backend
- [ ] OpenTelemetry traces flow into Grafana dashboards
- [ ] SLOs defined with alerting + on-call routing
- [ ] Unit + integration + E2E + load tests exist and gate CI
- [ ] Coverage threshold is enforced
