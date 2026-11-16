---
name: dry-run-first
description: Always dry-run DR migrations and show the plan before executing live
type: feedback
tags: dr, migration, safety
created: 2026-08-31
---

Never execute a live DR migration without first running `dr_migrate_service` with `dry_run=true` and showing the plan.

**Why:** A live failover shifts production traffic; the user must see and approve the plan first.
**How to apply:** On any migration request, dry-run first, present the steps, and wait for explicit confirmation. See [[order-service-migration]] for service-specific constraints.
