---
name: payment-service-drill
description: payment-service failed its 2026-07-12 DR drill on DNS failover; re-verify DNS before trusting a READY verdict
type: project
tags: dr, payment-service, dns
created: 2026-08-31
---

payment-service failed its DR drill on 2026-07-12 — DNS failover records did not propagate within the RTO window. The fix was applied on 2026-07-20 but has not been re-drilled.

**Why:** A healthcheck can report `dns_failover_configured: true` while propagation is still slow under load.
**How to apply:** When reporting payment-service failover readiness, flag that the last successful drill predates the DNS fix. See [[dr-runbook]].
