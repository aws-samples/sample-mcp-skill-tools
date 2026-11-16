---
name: pr-parallel-review
description: Reviews a PR with three specialist subagents (security, performance, correctness) running concurrently, then merges findings by severity.
trigger: "review this PR in parallel"
---

# Parallel PR Review

> Splits a PR review across three `pr-specialist` subagents so each dimension gets a full context window and the reviews run concurrently.

| | |
|---|---|
| **Trigger** | `"review this PR in parallel"` |
| **Type** | Multi-agent orchestration (Pattern C) |
| **Agents** | `agents/pr-specialist.md` × 3 (security, performance, correctness) |
| **Output** | Merged findings grouped by severity |

## Workflow Steps

### 1. Fan out (single message, parallel)

Spawn three `pr-specialist` subagents in the same message, prompts: `Review this PR for <dimension> only. PR: <number or branch>.` — one each for **security**, **performance**, **correctness**.

### 2. Merge findings

Deduplicate, then group by severity: **Critical** > **Warning** > **Suggestion**, tagging each finding with its dimension.

### 3. Confirm before posting

Show the merged list. Only post to the PR (`gh pr review --comment`) if the user confirms.

## Why this matters (context management)

Each specialist reads the full diff in its own context — three deep reads cost the supervisor only ~9 finding lines. Mirrors CAO's pattern of one worker profile receiving different assignments.
