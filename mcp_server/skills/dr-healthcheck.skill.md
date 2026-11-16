---
name: dr-healthcheck
description: Run a DR healthcheck on a service to verify failover readiness across regions. Returns replication lag, DNS config, backup status, and drill history.
execution_mode: shell
input_schema:
  type: object
  properties:
    service_name:
      type: string
      description: Name of the service to check
      pattern: "^[a-zA-Z0-9][a-zA-Z0-9._-]{0,63}$"
    region:
      type: string
      description: Target DR region to validate
      default: us-west-2
      pattern: "^[a-z]{2}-[a-z]+-[0-9]$"
  required:
    - service_name
output_schema:
  type: object
  properties:
    service:
      type: string
    region:
      type: string
    status:
      type: string
      enum: [healthy, degraded, unhealthy]
    failover_ready:
      type: boolean
    checks:
      type: object
    issues:
      type: array
      items:
        type: string
---

# DR Healthcheck

> Run a DR healthcheck on a service to verify failover readiness across regions.

## Parameters

| Name | Type | Required | Description |
|------|------|----------|-------------|
| `service_name` | string | Yes | Name of the service to check |
| `region` | string | No | Target DR region to validate (default: `us-west-2`) |

## Response

| Field | Type | Description |
|-------|------|-------------|
| `status` | `healthy` · `degraded` · `unhealthy` | Overall DR readiness |
| `failover_ready` | boolean | Whether the service can fail over now |
| `checks.database_replication_lag_ms` | number | Replication lag in milliseconds |
| `checks.dns_failover_configured` | boolean | DNS routing policy is active |
| `checks.backup_age_hours` | number | Hours since last backup |
| `checks.runbook_exists` | boolean | Runbook is published |
| `checks.last_dr_drill` | date | Most recent DR drill date |

## Execution

The reference DR control plane (`dr-control.internal.fakecompany.com`) is a
fake endpoint that does not resolve, so this demo skill emits a realistic,
schema-valid healthcheck payload locally via the allowlisted `echo` binary.
In a real deployment, swap this for the live `curl` call shown in the
**Live Endpoint** section below — the server transparently moves the
`DR_API_TOKEN` bearer header out of `argv` and delivers it over curl's
`--config -` stdin channel, so the credential never appears in the process
table or the LLM context.

```shell
echo '{"service":"${service_name}","region":"${region}","status":"healthy","failover_ready":true,"checks":{"database_replication_lag_ms":12,"dns_failover_configured":true,"backup_age_hours":2.4,"runbook_exists":true,"last_dr_drill":"2026-05-15"},"issues":[]}'
```

## Live Endpoint (production)

```
curl -s -H "Authorization: Bearer ${DR_API_TOKEN}" \
  "https://dr-control.internal.fakecompany.com/v1/healthcheck/${service_name}/${region}"
```

## Security

- Credentials (`DR_API_TOKEN`) are injected at runtime by the agent framework
- They are **never** passed into LLM context
- Input parameters are constrained by JSON Schema `pattern` rules and rendered
  into an argument array (no `shell=True`), preventing command injection
- The agent publishes this as a typed MCP tool at startup