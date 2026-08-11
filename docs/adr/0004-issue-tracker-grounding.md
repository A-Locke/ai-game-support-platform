# ADR 0004: Issue-Tracker Grounding (Jira, Azure DevOps)

| | |
|---|---|
| **Status** | Accepted |
| **Date** | 2026-08-11 |
| **Related** | [ai-workflows.md](../ai-workflows.md) · [ADR 0001, D7](0001-architecture-and-tech-stack.md#d7-structured-claude-output-via-forced-tool-use-not-prompt-embedded-json) |

## Context

The classification prompt's "known issue" grounding was, until now, entirely a static
`knowledge-base/known-issues/*.md` fixture — real for a demo, but not a real ticketing system.
The project owner confirmed this explicitly (asked whether the KI-014 match during live testing
was fabricated: yes, it was reading a bundled markdown file, not a live query) and asked for real
grounding against an actual Jira and/or Azure DevOps backlog, evaluated against several possible
implementation approaches (own Python orchestration, Anthropic's native MCP connector, Azure
Copilot Agents). Own orchestration via Python was chosen — see the evaluation this ADR
summarizes below — targeting both Jira and Azure DevOps, with the design-doc RAG piece
explicitly deferred to a later round.

## Decision Drivers

1. **No new agentic paradigm.** `ai-service` already builds prompt context before one forced
   Claude tool call (ADR 0001, D7); grounding should extend that step, not introduce a
   multi-turn agentic loop.
2. **Each source is independently optional.** A deployment might have Jira, Azure DevOps, both,
   or neither — matching the project's existing "empty config = skipped, not broken" pattern
   (`S3_BUCKET`, `ANTHROPIC_API_KEY`, etc.).
3. **Reuse official MCP servers, not custom REST clients**, consistent with brief §14's
   preference for official/reliable libraries over hand-rolled integration code.
4. **Never let a grounding-source failure block classification.** A Jira outage must degrade to
   "no grounding data," not crash the workflow.

## Options evaluated

| Option | Verdict |
|---|---|
| **Own orchestration via Python** (ai-service becomes an MCP client to Jira/Azure DevOps MCP servers, folding results into the existing prompt-building step) | **Chosen.** Direct extension of the existing `mcp_client.py` pattern; deterministic, testable, no new architecture. |
| **Anthropic's native MCP connector** (Claude autonomously calls remote MCP servers mid-turn via the Messages API) | Rejected for now. Trades away the predictability ADR 0001 deliberately chose a single forced tool call for — variable latency/cost, harder to unit test. Worth revisiting if classification ever needs genuinely open-ended multi-hop research. |
| **Azure Copilot Agents / Azure AI Foundry Agent Service** | Rejected. Means hosting the actual triage intelligence on Microsoft's agent platform instead of Claude, which conflicts with this project's core "Claude is the intelligence provider, self-hosted infra otherwise" design (ADR 0001) unless a project explicitly wants to swap off Claude for this piece. |

## Decisions

### D1: `ai-service` connects to Jira/Azure DevOps as an MCP client, using their official servers

**Decision:** `app/grounding.py` uses the same `fastmcp.Client` machinery `mcp_client.py` already
uses for `support-mcp-server`, pointed at Atlassian's official remote MCP server
(`atlassian/atlassian-mcp-server`, tool `searchJiraIssuesUsingJql`) and/or Microsoft's official
Azure DevOps MCP server (`microsoft/azure-devops-mcp`, tool `mcp_ado_search_workitem`), configured
via `JIRA_MCP_URL`/`JIRA_MCP_API_TOKEN` and `AZURE_DEVOPS_MCP_URL`/`AZURE_DEVOPS_MCP_PAT`.

**Why:** No custom REST client to maintain per tracker, and both servers are actively maintained
by their respective vendors rather than a third-party wrapper.

**Verification caveat, stated plainly:** unlike every other integration in this project, this one
has **not** been run against a real Jira or Azure DevOps instance — no credentials for either
were available in the environment this was built in. The tool names above are confirmed from each
project's own documentation as of 2026-08-11 (linked in PROJECT_JOURNAL.md, Milestone 6), but the
exact response *shape* each tool returns was not independently verified live. `_normalize_jira`
and `_normalize_ado` in `grounding.py` parse defensively (`.get()` with fallbacks, never assume a
field exists) specifically because of this — treat the first real run against your own Jira/Azure
DevOps instance as the actual verification step, and adjust the normalizers if a real response
shape differs from what's assumed.

### D2: Grounding results are folded into the existing prompt, not a second Claude call

**Decision:** `claude_client.py`'s `_build_prompt` gains a grounding section (real Jira/Azure
DevOps matches, when configured) alongside the existing static knowledge-base excerpt. Still one
forced tool call to Claude, same as before.

**Why:** Keeps ADR 0001, D7's single-deterministic-call design intact — grounding is richer
*context*, not a reason to change the call shape.

### D3: Each source fails independently and silently degrades

**Decision:** `_search_jira` and `_search_azure_devops` each catch their own exceptions and
return an empty result on any failure (network, auth, unexpected response shape) rather than
propagating. A grounding-source outage never blocks or crashes classification — see D4.

**Why:** Matches the project's existing philosophy (ADR 0001's Claude-call fallback, D6/D7's
graceful-if-unconfigured patterns elsewhere) — an optional context-enrichment step degrading
gracefully to "no extra context" is a completely different failure mode from something the
workflow actually depends on.

### D4: The Claude-routine (MCP-only) mode gets the same sources for free

**Decision:** No new code needed for `.claude/commands/process-support-queue.md` — a Claude Code
session can add the same official Jira/Azure DevOps MCP servers as additional connectors
alongside `support-mcp-server` and use them directly during the routine, the same way the
project owner drove `support-mcp-server` directly in Milestone 2.

**Why:** This is ADR 0001's client-agnostic MCP design paying off again (see ADR 0003's whole
premise) — official servers exist for exactly this, so the MCP-only mode needs documentation,
not new code.

## Consequences (Overall)

**Positive:** Real grounding is possible without inventing a bespoke Jira/Azure DevOps client;
each source is fully optional and independently configurable; the Claude-routine mode gets the
same capability with zero new code.

**Negative / accepted trade-offs:** This integration's response-parsing logic is the one piece of
this project shipped without a live-credentials test — flagged explicitly rather than silently
assumed correct. The design-doc RAG piece (originally part of the same request) is deferred; no
official MCP server exists for it, so it would need a real build, not just configuration, when
picked back up.
