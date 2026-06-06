# ADR 0001: Record architecture decisions

We use lightweight Architecture Decision Records (ADRs) in `docs/adr/` to capture **why** we chose an approach, not just **what** shipped.

## Template for new ADRs

1. Copy this file to `NNNN-short-title.md` (next number).
2. Fill in **Context**, **Decision**, **Consequences**, and **Status** (Proposed | Accepted | Superseded).

## ADR index

| # | Title | Status |
|---|-------|--------|
| 0001 | Record architecture decisions (this file) | Accepted |

Roadmaps and phased execution live in [`../production-grade-plan.md`](../production-grade-plan.md) and [`../phases/`](../phases/).

## Context

The monorepo spans web, mobile, and API. Without written decisions, trade-offs get lost in PR noise.

## Decision

- Store ADRs as Markdown in `docs/adr/`.
- Link long-running roadmaps from `docs/` and per-phase files from `docs/phases/`.

## Consequences

- Engineers and reviewers can align on intent before debating implementation details.
