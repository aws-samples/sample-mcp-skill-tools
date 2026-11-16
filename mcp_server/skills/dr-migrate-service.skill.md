---
name: dr-migrate-service
description: Migrate a service across regions for DR failover. Validates capacity, replication, DNS, and traffic shifting. Defaults to dry-run mode for safety.
execution_mode: shell
input_schema:
  type: object
  properties:
    service_name:
      type: string
      description: Name of the service to migrate
      pattern: "^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$"
    source_region:
      type: string
      description: Current region the service runs in
      pattern: "^[a-z]{2}-[a-z]+-[0-9]$"
    target_region:
      type: string
      description: DR region to fail over to
      pattern: "^[a-z]{2}-[a-z]+-[0-9]$"
    dry_run:
      type: boolean
      description: If true, validates the plan without executing. Default true.
      default: true
  required:
    - service_name
    - source_region
    - target_region
output_schema:
  type: object
  properties:
    service:
      type: string
    status:
      type: string
      enum: [dry_run_complete, migration_in_progress, migration_complete, failed]
    steps:
      type: array
      items:
        type: object
    estimated_downtime_seconds:
      type: number
    rollback_available:
      type: boolean
---

# DR Migrate Service

> Migrate a service across regions for DR failover. Validates capacity, replication, DNS, and traffic shifting. Defaults to dry-run mode for safety.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `service_name` | string | Yes | Name of the service to migrate |
| `source_region` | string | Yes | Current region the service runs in |
| `target_region` | string | Yes | DR region to fail over to |
| `dry_run` | boolean | No | Validate plan without executing (default: `true`) |

## Response

| Field | Type | Description |
|-------|------|-------------|
| `status` | `dry_run_complete` · `migration_in_progress` · `migration_complete` · `failed` | Current migration state |
| `steps` | array | Ordered list of validation/execution steps |
| `estimated_downtime_seconds` | number | Expected downtime (0 for blue-green) |
| `rollback_available` | boolean | Whether rollback is possible |

## Execution

The reference DR migration engine (`dr-migrate.internal.fakecompany.com`) is a
fake endpoint that does not resolve, so this demo skill emits the realistic,
schema-valid payload locally via the allowlisted `echo` binary. The output
mirrors the reference implementation: a **dry-run plan**
(`status: dry_run_complete`, step 5 `ready`) when `dry_run=true`, and a **live
failover** response (`status: migration_in_progress`, step 5 `in_progress`)
when `dry_run=false`. Mode selection uses `${dry_run ? ... : ...}` conditional
tokens resolved by the server before command execution.

In a real deployment, swap this for the live `curl` call in the **Live Endpoint**
section below — the server moves the `DR_API_TOKEN` bearer header out of `argv`
and delivers it over curl's `--config -` stdin channel, so the credential never
appears in the process table or the LLM context.

```shell
echo '{"service":"${service_name}","source_region":"${source_region}","target_region":"${target_region}","dry_run":${dry_run ? true : false},"status":"${dry_run ? dry_run_complete : migration_in_progress}","message":"${dry_run ? Migration plan validated. No resources were modified. : Failover initiated. Traffic shifting to target region.}","steps":[{"step":1,"action":"Verify target region capacity","result":"passed"},{"step":2,"action":"Check database replication sync","result":"passed"},{"step":3,"action":"Validate DNS routing policies","result":"passed"},{"step":4,"action":"Pre-warm target instances","result":"passed"},{"step":5,"action":"Shift traffic (0% -> 100%)","result":"${dry_run ? ready : in_progress}"}],"estimated_downtime_seconds":0,"rollback_available":true}'
```

## Live Endpoint (production)

```
curl -s -X POST -H "Authorization: Bearer ${DR_API_TOKEN}" \
  -H "Content-Type: application/json" \
  -d '{"dry_run": ${dry_run}}' \
  "https://dr-migrate.internal.fakecompany.com/v1/migrate/${service_name}/${source_region}/${target_region}"
```

## Security

- Defaults to `dry_run=true` — no resources are modified unless explicitly set to `false`
- Credentials (`DR_API_TOKEN`) are injected at runtime by the agent framework
- They are **never** passed into LLM context
- Input parameters are constrained by JSON Schema `pattern` rules and rendered
  into an argument array (no `shell=True`), preventing command injection
- Rollback is available for 24 hours after a live migration