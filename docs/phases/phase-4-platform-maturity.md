# P4 — Platform Maturity & Top-Tier

**Duration:** Week 11–16
**Goal:** Reach A+/O on every remaining dimension — reproducible infra, zero-downtime deploys, RBAC, data resilience, compliance, and governance.

> Related: [`../architecture-review.md`](../architecture-review.md) · [`../production-grade-plan.md`](../production-grade-plan.md)

## Why this phase
This is what separates "production-ready" from "top-tier." It makes the platform reproducible, recoverable, least-privilege, compliant, and operable by any engineer from docs alone.

## Workstreams

| Workstream | Tasks | Exit criteria |
|---|---|---|
| Infra as code + deploys | Terraform; managed Postgres; ECS/K8s; blue-green/canary with auto-rollback; multi-env promotion. | Zero-downtime deploys; infra is reproducible. |
| AuthZ & admin plane | Roles/permissions beyond owner-only; a separated admin surface. | Least-privilege enforced. |
| Data resilience | PITR backups, read replicas as needed, verified encryption in transit + at rest, DR drill. | RPO/RTO targets met in a drill. |
| Compliance & privacy | Data-handling review (PCI-adjacent), data-subject export/delete, retention policy, WAF, feature flags. | Privacy + security review signed off. |
| Governance | Contract tests, SBOM, runbooks, an ADR catalog kept current. | A new engineer can operate the system from docs. |

## Prerequisites
- **P3** complete (observability + tests), so deploys, SLOs, and DR drills can be measured and verified.

## Dimensions advanced (all reach A+/O)
- **Scalability / infra:** A- → A+ (IaC + orchestration + zero-downtime deploys)
- **Code structure / layering:** A- → A+ (governance + ADRs + contract tests)
- **Auth / AuthZ:** A → A+ (RBAC + admin plane)
- **Compliance / privacy / governance:** A- → A+ (export/delete, retention, DR, runbooks)
- **Data modeling & resilience:** A → A+ (PITR, replicas, encryption verified)

## Phase completion checklist
- [ ] Infra is fully defined in Terraform; environments are reproducible
- [ ] Deploys are zero-downtime (blue-green/canary) with auto-rollback
- [ ] RBAC + separated admin plane enforce least privilege
- [ ] PITR backups, replicas, and verified encryption in place; DR drill passes
- [ ] Data-subject export/delete, retention policy, and WAF live
- [ ] SBOM, runbooks, contract tests, and ADR catalog are current
- [ ] Every dimension sits at A+/O per the acceptance bar
