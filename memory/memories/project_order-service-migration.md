---
name: order-service-migration
description: order-service migrations require paging the DB team FIRST, before initiating any failover.
type: project
tags: dr, order-service, migration, db-team
created: 2026-09-03
---

order-service migrations require paging the DB team FIRST, before initiating any failover.

**Why:** order-service is a data-tier service; the DB team must be engaged before traffic shifts to avoid data-sync issues during cutover.
**How to apply:** On any order-service migration request, page the DB team (DB team pager; #dr-oncall Slack) and confirm engagement before running a live dr_migrate_service. Dry-run and plan review still apply first. See [[dr-runbook]] and [[dry-run-first]].
