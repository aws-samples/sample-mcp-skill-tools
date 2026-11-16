---
name: pull-request-description
description: Generate high-quality, industry-standard GitHub Pull Request descriptions from context the user provides (branch name, Jira ticket, diff summary, or a plain description of changes). Use this skill whenever the user asks to write, draft, create, or improve a PR description, pull request body, or PR template. Also trigger when the user says things like "write my PR", "help me describe this change", "draft a pull request for", or "fill out the PR template". Also use this skill when updating an existing PR description after reviewer feedback or new commits (e.g. "update the PR description", "addressed review comments"). Even if the user gives only a brief summary of changes, use this skill to produce a complete, well-structured PR description.
trigger: "write my PR description"
---

# Pull Request Description Skill

Produce complete, reviewer-ready GitHub Pull Request descriptions following the team's conventions and industry best practices.

## Workflow Steps

Follow these steps in order. The detailed reference material for each step lives
in the sections below (**Inputs to gather**, **PR Title**, **Output Template**,
**Writing Guidelines**). No side-effecting action (writing to a PR, pushing,
posting a comment) happens before the confirmation step.

### 1. Gather the required inputs
- Extract the Jira ticket ID, what changed, and why from the conversation, branch name, and commit messages (see **Inputs to gather**).
- Ask the user only for inputs that cannot be inferred — especially the mandatory test evidence.
- Do not invent a Jira ID; if none exists, request one before continuing.

### 2. Compose the PR title
- Format the title as `JIRA-XXX: <imperative summary>` per the **PR Title** rules.
- Keep it under 72 characters and avoid Conventional Commits prefixes.

### 3. Draft the full description
- Populate every section of the **Output Template**, filling What, Why, How, and testing details.
- Apply the **Writing Guidelines** (concrete file names, operational impact, exact test commands).
- Insert an explicit placeholder for test evidence if the user has not supplied it.

### 4. Present the draft for confirmation
- Show the user the complete drafted title and description.
- Verify the five checklist items are present and verbatim.
- Ask: "Apply this PR description? (yes/no)" — and proceed to any write action ONLY on an explicit affirmative. If the user declines or is silent, stop and offer revisions.

### 5. Apply and report
- Only after confirmation, write the description to the target (e.g. `gh pr edit`/`gh pr create`) or hand the finalized markdown to the user.
- Report what was applied and remind the user the PR is not ready to submit until test evidence is attached.

## Inputs to gather

Before writing, extract as much as possible from the conversation. Ask only for what's truly missing.

| Input | Required | Source |
|---|---|---|
| Jira ticket ID (e.g. `JIRA-503`) | Yes | User, branch name, or commit message |
| What changed (files, logic, schema) | Yes | User description or diff |
| Why the change was needed | Yes | Jira ticket context or user explanation |
| How it was implemented (key technical details) | Recommended | User |
| Testing performed | Recommended | User |
| Test evidence (screenshots, logs, terminal output) | Yes | User |

If the Jira ID is embedded in the branch name (e.g. `JIRA-503-kafka-connectivity-test`), extract it automatically. Do not ask the user for it.

## PR Title

The title MUST follow this format — no exceptions:

```
JIRA-XXX: Short description
```

Where `JIRA-XXX` is the Jira ticket ID (e.g. `JIRA-503`) followed by a colon, a space, and a short imperative summary.

Examples:

- `JIRA-503: Add Kafka MSK connectivity test via Lambda`
- `JIRA-610: Deduplicate stream consumer events on upsert`
- `JIRA-672: Clean up DynamoDB tables on PR deletion`

Keep the title under 72 characters. Do not use Conventional Commits prefixes (`feat:`, `fix:`, etc.) — the Jira ID replaces them. If no Jira ticket exists, ask the user for one before writing the title.

## Output Template

Always produce the full template below. Fill every section; use `N/A` only if genuinely not applicable.

```markdown
## Checklist
🔴 Please review this repository's [contribution guidelines](CONTRIBUTING.md).

- [ ] I've read and agree to the project's contribution guidelines.
- [ ] I'm requesting to **pull a topic/feature/bugfix branch**.
- [ ] I checked that my code additions will pass code linting checks and unit tests.
- [ ] I updated unit and integration tests (if applicable).
- [ ] I'm ready to notify the team of this contribution.

---

## Description

### Resolves: TICKET-ID

### What does this change do and why?

**What:**
*(Bullet list of the specific files/components changed and what was done to them.)*
- Updated `file_a.py` to ...
- Added `file_b.py` for ...

**Why:**
*(The problem this solves and its business or operational impact.)*

**How:**
*(Key implementation details reviewers need to understand the approach.)*

---

### How to Test and Validate

**Automated Tests:**
- `<command to run new/existing tests>`
- All existing tests pass: `<suite command>`

**Manual Verification:**
1. ...
2. ...
3. **Expected Result:** ...

---

### Test Evidence (required)

*(Screenshots of test runs, log snippets, or terminal output proving the change works are MANDATORY. A PR description is incomplete without them.)*

---

TICKET-ID

Thank you!
```

## Writing Guidelines

- **What** bullets should name concrete files or components, not vague descriptions. ✅ "Updated `handler.py` to emit `observer.lambda.duration_ms` to Cloudwatch" ❌ "Changed the handler"
- **Why** must convey operational or business impact, not just restate what. ✅ "Without this, the Lambda has no health signal in Cloudwatch, making incidents invisible" ❌ "Adds metrics"
- **How** should call out non-obvious decisions: threading model, retry logic, schema migration approach, CDK construct choices, etc.
- For infrastructure/CDK PRs, note whether the change requires a deploy step or stack update.
- For DynamoDB PRs, note whether the schema change is backward compatible and how existing data is handled.
- Testing section must include the exact command to run tests, not just "tests were added".
- Link the Jira ticket twice: once in the `Resolves:` line and once at the bottom (team convention).
- **Checklist validation:** Always output the exact five checklist items from the template above, verbatim. If the user pastes or edits a description, verify all five items are present and correctly worded; restore any that are missing or altered.
- **Test evidence is mandatory:** Never mark the Test Evidence section as `N/A` or optional. If the user hasn't provided screenshots or test output, leave an explicit placeholder (e.g. `<!-- TODO: attach test run screenshot -->`) and remind them the PR isn't ready to submit without it.
