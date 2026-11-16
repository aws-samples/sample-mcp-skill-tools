# Skill-Tools MCP Pattern

A reference implementation showing how to extend AI coding agents with custom,
governed "skills" using the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/)
and Markdown-based workflow playbooks.

Each skill is a `.skill.md` file: YAML frontmatter (name, description, JSON Schema
for inputs/outputs) plus a Markdown body containing a single allowlisted shell
command template. At startup the server parses these files and registers each as
a typed MCP tool. At call time, user parameters are validated against the schema,
substituted into the command via a safe (no-shell) argument array, and executed
against an allowlist of binaries. Credentials are loaded from AWS Secrets Manager
and delivered out of band so they never appear in process arguments, the child
environment, or the model context.

> **Disclaimer**
>
> This is sample code, for non-production usage. You should work with your
> security and legal teams to meet your organizational security, regulatory, and
> compliance requirements before deployment.

## Architecture

See [`diagrams/architecture.png`](diagrams/architecture.png) and
[`diagrams/injection-defense.png`](diagrams/injection-defense.png).

## Extension patterns

This repository demonstrates several complementary ways to extend an agent. The
core pattern is the governed MCP tool; the others build on it to manage context,
persist knowledge, and assemble live views.

| Pattern | Where it lives | What it does |
|---|---|---|
| **Callable MCP tools** | `mcp_server/skills/*.skill.md` | Declarative `.skill.md` files registered as typed MCP tools at startup, executed against an allowlist with out-of-band credentials |
| **Dev-workflow playbooks** | `dev-workflows/*.skill.md` | Markdown the agent reads and follows step-by-step (no server compilation) |
| **C — Multi-agent orchestration** | `multi-agent/*.skill.md` + `multi-agent/agents/*.md` | A supervisor fans out parallel specialist subagents; only their one-line verdicts return, keeping the main context clean |
| **D — Persistent memory** | `memory/memory.skill.md` + `memory/` | Facts stored in one session are recalled in the next, backed by markdown files with a `MEMORY.md` index |
| **E — Live artifacts** | `live-artifacts/live-artifacts.skill.md` | Assembles a standup check-in or demo overview by re-querying connected tools (Jira, GitHub, Slack) at open time, not from a stale snapshot |

### C — Multi-agent orchestration

Every verbose tool response normally lands in the main conversation and stays
there for the whole session. Instead, the supervisor delegates to **specialist
subagents** defined in `multi-agent/agents/` — each runs in its own
fresh context window, does the heavy reading, and returns only a conclusion.
`dr-fleet-audit` spawns
one `dr-auditor` per service (each digests the raw `dr_healthcheck` JSON and
returns one verdict row); `pr-parallel-review` spawns three `pr-specialist`s
(security / performance / correctness) whose findings are merged by severity.
This is the same supervisor/worker model as
[CLI Agent Orchestrator (CAO)](https://github.com/awslabs/cli-agent-orchestrator),
using native subagents instead of tmux-managed sessions.

### D — Persistent memory

Two MCP tools — `memory_store` and `memory_recall` — back a plain-markdown
store under `memory/`. `memory_store` writes
`memory/memories/{type}_{key}.md` with frontmatter and appends a line
to `memory/MEMORY.md`; `memory_recall`
keyword-searches the files and returns ranked matches. The `memory.skill.md`
playbook tells the agent to recall automatically before DR migrations and
readiness reports, and to store immediately when the user states a constraint or
correction. See the playbook's *Wiring the tools into this pattern's MCP server*
section for how the two functions integrate with `mcp_server/server.py` while
keeping the repository's fail-closed and redaction posture.

### E — Live artifacts

A live artifact is not a static export — each section names its source tool and
is re-queried at open time, so the page always reflects the current sprint
state. `live-artifacts.skill.md` drives a daily standup check-in and a sprint
demo overview from Jira, GitHub, and Slack, replacing the daily context-switch
across those tools. Reference images live in `live-artifacts/assets/`.

## Quick start

```bash
# 1. Create a virtual environment and install dependencies
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 2. Configure MCP settings
# Edit .mcp.json — set SKILL_TOOLS_SECRET to your Secrets Manager secret name.
# For local testing without AWS, set SKILL_TOOLS_SECRET=__mock__.

# 3. Run the tests
SKILL_TOOLS_SECRET=__mock__ .venv/bin/pytest tests/ -q
```

## Project structure

```
.
├── mcp_server/
│   ├── server.py              # MCP server: registration, validation, safe execution
│   ├── parser.py              # .skill.md frontmatter/body parser
│   ├── secrets_loader.py      # AWS Secrets Manager credential loader (fail-closed)
│   └── skills/                # Skill definitions (.skill.md) — callable MCP tools
├── dev-workflows/             # Markdown workflow playbooks
│   └── pull-request-description.skill.md
├── multi-agent/               # Multi-agent orchestration (Pattern C)
│   ├── dr-fleet-audit.skill.md        # Parallel fan-out: one dr-auditor per service
│   ├── pr-parallel-review.skill.md    # Parallel fan-out: 3 pr-specialists
│   └── agents/                        # Subagent profiles
│       ├── dr-auditor.md              # Audits ONE service, returns one verdict line
│       └── pr-specialist.md           # Reviews ONE dimension of a diff
├── memory/                    # Persistent cross-session memory (Pattern D)
│   ├── memory.skill.md                # Memory store/recall usage playbook
│   ├── MEMORY.md                      # One-line index of all memories
│   └── memories/                      # One markdown file per memory
├── live-artifacts/            # Live cross-tool artifacts (Pattern E)
│   ├── live-artifacts.skill.md        # Standup check-in + demo overview
│   └── assets/                        # Reference images
├── iam/                       # Least-privilege IAM policy for the secret
├── tests/                     # Unit tests
├── diagrams/                  # Architecture and injection-defense diagrams
└── .mcp.json                  # MCP server config template
```

## Security

This pattern's security controls:

- **Command allowlist** — only `curl`, `aws`, `kubectl`, `psql`, `echo` may run.
- **No shell** — commands run via an argument array (`shell=False`); user input is
  never interpolated into a shell string.
- **Input validation** — JSON Schema `pattern` constraints reject malformed input.
- **Credential isolation** — secrets come from AWS Secrets Manager and are delivered
  out of band (curl `--config -` stdin), never in `argv` or the environment.
- **Output redaction** — credential values are scrubbed from command output.

See [CONTRIBUTING](CONTRIBUTING.md#security-issue-notifications) for how to report
security issues.

## License

This library is licensed under the MIT-0 License. See the [LICENSE](LICENSE) file.
