---
name: memory
description: Persistent cross-session memory via memory_store and memory_recall MCP tools, backed by markdown files with a MEMORY.md index.
trigger: "remember that ..." / "what do you remember about ..."
---

# Memory

> Gives the agent persistent, cross-session storage. Facts stored in one session are recalled in the next. Same store → inject → recall loop as CLI Agent Orchestrator (CAO), backed by plain markdown files instead of a SQLite-indexed wiki.

| | |
|---|---|
| **Store trigger** | `"remember that <fact>"` |
| **Recall trigger** | `"what do you remember about <topic>"` — plus automatic recall (below) |
| **Type** | MCP tools (Pattern A) + usage playbook (Pattern B) |
| **Storage** | `memory/memories/*.md` + `memory/MEMORY.md` index |

## Tools

| Tool | Signature | What it does |
|---|---|---|
| `memory_store` | `(content, key?, memory_type?, tags?)` | Writes/updates `memory/memories/{type}_{key}.md` with frontmatter and appends a line to `MEMORY.md` |
| `memory_recall` | `(query?, memory_type?, limit?)` | Keyword search over memory files; returns matches with metadata and `_meta` block |

## Memory types

| Type | Use for |
|---|---|
| `project` | Service state, architecture decisions, drill history |
| `feedback` | Corrections and confirmed approaches — include **Why** and **How to apply** |
| `user` | Preferences and working style |
| `reference` | Runbooks, dashboards, tickets, URLs |

Type is a classification label only — every memory lands in the same `memories/` directory (CAO's scope-vs-type distinction, simplified to a single project scope).

## When to store

Store immediately when the user corrects you, states a constraint ("always X before Y"), or says "remember that ...". Keep each memory to 1–3 sentences: the decision, not the conversation. Convert relative dates to absolute.

## When to recall (automatic)

- **Before any DR migration or readiness report**: `memory_recall(query="<service-name>")` and apply/flag whatever comes back.
- **When asked about prior work or decisions**: recall before answering "I don't know."

## Presenting the result

Digest the tool's JSON response in your own context — **never print the raw `memory_recall` / `memory_store` payload or the tool-call mechanics to the conversation.**

- **Recall**: summarize matches as a short bulleted list — `key` + one-line relevance — and apply/flag them inline in your answer. Don't dump the `content`/`_meta` JSON.
- **Store**: confirm in one line — what was remembered and its `key` (e.g. "Stored as `order-service-migration` (project)."). Don't echo the file frontmatter.

## File format

```markdown
---
name: <kebab-case-key>
description: <one line, used to judge relevance at recall>
type: project | feedback | user | reference
tags: <comma-separated>
created: <YYYY-MM-DD>
---

<fact>

**Why:** <rationale>
**How to apply:** <action>. Related: [[other-memory-name]].
```

## Wiring the tools into this pattern's MCP server

Unlike the DR skills, the memory tools read and write the local
`memory/` store rather than calling an allowlisted binary, so they are
registered as two functions on the same MCP server rather than as declarative
`## Execution` skill files. Register `memory_store` and `memory_recall`
alongside the existing tools in `mcp_server/server.py`, pointing `MEMORY_DIR` at
`memory/memories/` and `MEMORY_INDEX` at `memory/MEMORY.md`.
Keep the same fail-closed and output-redaction posture as the rest of the
server: validate `memory_type` against the four allowed labels, derive the file
name from a sanitized `key`, and never write outside the `memory/`
directory.
