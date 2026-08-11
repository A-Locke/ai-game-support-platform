# Project Journal

Chronological record of milestones, technical decisions, blockers, resolutions, and lessons
learned. ADRs capture the *what/why* of individual decisions in detail (see
[`docs/adr/`](docs/adr/)); this journal captures the narrative and sequencing.

---

## Milestone 0 — Brief ingestion and architecture docs

**Status:** in progress
**Date started:** 2026-08-10

### Decisions

- **Brief ingestion, not brief retention.** `ai_augmented_game_support_technical_task.md` is
  the originating tech task. Its content is being ingested section-by-section into
  `docs/architecture.md`, `docs/ai-workflows.md`, `docs/mcp-server.md`, `docs/setup.md`,
  `docs/cost-estimate.md`, and `docs/adr/0001-architecture-and-tech-stack.md`. The source file
  is deleted once that ingestion is complete and never committed to git — a deliberate choice
  stated up front by the project owner so the repo doesn't carry the brief as a permanent
  artifact once its content has a real home in normal docs.
- **Docs before implementation.** At the project owner's explicit direction, the architecture
  docs and ADR are written first, and this journal is kept current milestone-by-milestone as
  implementation proceeds — not written retroactively at the end.
- **Mid-build architecture revision: MCP server targets Google Cloud Run.** The original plan
  (single VM, Docker Compose for everything) is still the default recommended cloud path, but
  the project owner flagged that the MCP server specifically may run on Cloud Run, which bills
  per-request and needs to scale to zero. That ruled out the legacy SSE transport and any
  server-side session state, which cascaded into also removing local dedup storage from
  ai-service (see ADR 0001, decisions D2, D5, D6) so both custom services can deploy the same
  way. Reference implementations for the fastmcp-on-Cloud-Run shape:
  `Work/Projects/QA/UseResponse` and `Work/Projects/QA/UnrealTestRail`.

- **Demo game renamed from the brief's suggested "Ashfall" to "Generic."** The brief's own
  example name collides with both an existing film and an existing game studio; the project
  owner asked for a deliberately generic placeholder instead, on the nose enough that no reader
  could mistake it for a real title.

### Blockers & resolutions

None yet.

### Known limitations

- No code has been run yet as of this entry — `docs/setup.md`'s command sequences are design
  intent until Milestone 1/2 verify them against a real `docker compose up`.

---

## Milestone 1 — Implementation, both services, and a real `docker compose up`

**Status:** complete
**Date started:** 2026-08-10
**Date completed:** 2026-08-10

### What was built

`mcp-server` (fastmcp, 11 tools, bearer-auth Streamable HTTP + stdio, 17 passing pytest tests)
and `ai-service` (FastAPI webhook receiver, forced-tool-call Claude classification, MCP client,
four workflow modules, reporting endpoint, 19 passing pytest tests) — both against real
installed dependencies (`fastmcp` 3.4.7, `anthropic` 0.121.0), not assumed APIs. Game data
("Generic" — see the rename note above), `docker-compose.yml`, both Dockerfiles, the Caddy cloud
overlay, and the two host-side setup/demo scripts were written to match.

### Verified live, not just unit-tested

Docker was available in this environment, so the full stack was actually brought up rather than
left as untested docs: `docker compose build` for both custom images, then `docker compose up`
for all six services (postgres, redis, chatwoot, chatwoot-sidekiq, mcp-server, ai-service), all
reaching a healthy state. Confirmed live over real HTTP, not mocked: `mcp-server`'s bearer auth
(401 with no/wrong token), `ai-service`'s webhook shared-secret check (401 on mismatch),
`ai-service` calling `mcp-server` over Streamable HTTP as a real MCP client, and that call
reaching the real Chatwoot container's API (confirmed by getting a real `401 Invalid Access
Token` back from Chatwoot itself when using a placeholder token, propagated correctly as a
structured error all the way back through the stack). Docker Desktop was not running at the
start of this session and was started specifically for this validation.

### Blockers & resolutions

Three real bugs were caught only by actually booting the stack, not by reading the Chatwoot
image's docs (which don't cover this level of detail):

1. **`docker/entrypoints/sidekiq.sh` doesn't exist.** The compose file originally pointed the
   `chatwoot-sidekiq` service at that path, assumed from a half-remembered older Chatwoot
   layout. Inspecting the actual image (`docker run --rm --entrypoint sh chatwoot/chatwoot:latest
   -c "find docker -type f"`) showed only `docker/entrypoints/rails.sh`, which is a generic
   wait-for-postgres wrapper that `exec`s whatever command it's given — the Procfile's `worker:`
   line confirmed sidekiq is meant to run through the *same* entrypoint with a different command,
   not a dedicated script. Fixed by pointing both `chatwoot` and `chatwoot-sidekiq` at
   `rails.sh` with their respective commands.
2. **Migrations don't run automatically.** `rails.sh` only waits for Postgres and `bundle
   check`s — it does not run `db:chatwoot_prepare`. That's a separate `release:` phase in the
   image's own `Procfile`, which Heroku-style platforms run automatically but Docker Compose
   does not. Added a one-shot `chatwoot-prepare` service (same image, `bundle exec rails
   db:chatwoot_prepare`) that `chatwoot` and `chatwoot-sidekiq` depend on via
   `condition: service_completed_successfully`.
3. **`extension "vector" is not available`.** `db:chatwoot_prepare` failed against plain
   `postgres:16-alpine` — current Chatwoot's schema requires the pgvector extension (used by its
   native AI/RubyLLM features, visible in the same startup logs). Switched the `postgres`
   service to the `pgvector/pgvector:pg16` image, which is exactly `postgres:16` with pgvector
   preinstalled; no other change needed. Also added the missing `POSTGRES_PORT=5432` env var
   that `rails.sh`'s own `pg_isready` wait loop reads (previously unset, working by accident
   only because `pg_isready` degraded gracefully with an empty `-p`).

None of these were guessable from documentation alone — each came from reading the actual
container's real error output.

### Known limitations

- The Chatwoot first-admin creation step is an unavoidable manual browser action (Chatwoot has
  no API for creating the very first account), so `scripts/configure_chatwoot.py` and
  `scripts/run_demo.py` were validated by careful reading and `py_compile`, not a full live run
  against a real API token — that remains true until someone completes the onboarding wizard by
  hand. Everything upstream of that step (image builds, all six containers reaching healthy,
  real auth checks on both `mcp-server` and `ai-service`, and a real — if intentionally
  unauthenticated — Chatwoot API round trip) was verified live.
- No screenshots exist; `docs/screenshots/` was removed rather than committed empty.

---

## Milestone 2 — Full interactive test pass, real credentials, real bugs

**Status:** complete
**Date started:** 2026-08-11
**Date completed:** 2026-08-11

### What happened

The project owner asked to actually test the running platform. Milestone 1's manual-onboarding
gap was closed live: the owner completed the Chatwoot admin wizard by hand and provided a real
API token. Rather than configure `ANTHROPIC_API_KEY` (no key was available), the owner proposed
registering `mcp-server` as a project-scoped MCP connector (`.mcp.json`, gitignored — it embeds
a real bearer token and is a testing convenience, not part of the deliverable) so this Claude
Code session could drive the MCP tools directly, standing in for `ai-service`'s own Claude calls.
That let real classification happen with zero API dependency, and — more importantly — put
every real HTTP hop under direct observation instead of behind a mocked test.

That observation surfaced six real bugs, none of which the 36 passing unit tests from Milestone
1 had caught, because each one only shows up when both real services talk to a real Chatwoot at
once:

1. **Chatwoot blocks webhooks to any private-network destination by default.** Registering
   `ai-service`'s webhook produced `WARN -- : Exception: Invalid webhook URL ... Hostname
   'ai-service' has no public ip addresses` in the Sidekiq logs -- the `ssrf_filter` gem Chatwoot
   uses for outgoing webhook delivery rejects RFC1918 ranges by default, which covers every other
   container on the same Compose network regardless of hostname. Root-caused by reading
   Chatwoot's own source inside the image (`lib/safe_fetch.rb`, `lib/safe_fetch/fetcher.rb`),
   which turned up an intentional, documented escape hatch:
   `SAFE_FETCH_ALLOW_PRIVATE_NETWORK=true`. Added to `docker-compose.yml`'s `chatwoot-env`
   anchor. Without this, the entire automated webhook pipeline was silently dead on arrival for
   any same-network deployment -- Docker Compose locally, and the single-VM cloud path both.
2. **`get_conversation_messages`' message_type is an integer, not the string ai-service checked
   for.** `ai-service/app/workflows/classify.py`'s `_extract_player_messages` compared
   `m.get("message_type") == "incoming"`. Chatwoot's Application API returns the raw enum (`0`
   for incoming); only the *webhook payload* separately serializes a string label. Confirmed by
   inspecting a real Sidekiq `WebhookJob` payload directly. Every real conversation's messages
   silently filtered down to zero, meaning Claude never got the actual player content. Fixed to
   accept both `0` and `"incoming"`; the test fixture that had been asserting the wrong (string)
   shape was fixed too, since it had been quietly validating the bug, not the behavior.
3. **A missing/empty `ANTHROPIC_API_KEY` crashed the webhook handler instead of degrading.** The
   anthropic SDK raises a plain `TypeError` from request *construction*, before any HTTP call,
   when the key is empty -- `except APIError` never saw it, so the first real webhook delivery
   500'd. Broadened both `claude_client.py` exception handlers to catch `Exception`, with a
   regression test that intentionally calls with no respx mock (so a real network attempt would
   fail the test, proving the error really is pre-flight).
4. **`set_conversation_attributes`'s MCP schema was too narrow.** Declared as `dict[str, str]`;
   `ai-service` legitimately sends a float (`ai_confidence`) alongside a string (`ai_category`)
   in the same call. A cross-service contract mismatch that neither service's own unit tests
   could catch alone, since each side's tests only exercised its own assumptions about the other.
   Widened to `dict[str, str | float | bool]`.
5. **Chatwoot's labels endpoint replaces the label set, it doesn't add to it.** Tagging "crash"
   then separately tagging "human-escalated" on the same conversation left only
   "human-escalated" -- confirmed by watching a real conversation's labels collapse after
   `create_draft_response`'s internal "ai-draft" tag call. `add_conversation_labels` now reads
   the current labels first and unions before writing, so the tool actually does what its name
   says.
6. **The reporting tools' Chatwoot filter payload produced invalid SQL.** `query_operator` is
   the *joiner between* condition i and i+1, not a per-condition flag -- it needs to be set on
   every condition except the last, not just the first. A 3-condition filter (date range +
   label) left conditions 2 and 3 unjoined, and Chatwoot 500'd with a raw
   `PG::SyntaxError: ... EXISTS (SE...`, visible directly in the Rails log. Replaced the
   ad hoc condition-building in both reporting tools with a shared `_date_range_conditions`
   helper that places `query_operator` correctly regardless of how many extra conditions are
   appended.

A seventh issue was found in `scripts/run_demo.py` by inspection once (1) was understood: its
conversation-seeding helper used the Application API's `message` shortcut on conversation
creation, which (confirmed live) creates that seed message as *outgoing* (agent-authored), not
incoming -- meaning the demo script's seeded tickets would never have triggered the automated
pipeline at all, silently. Rewritten to use Chatwoot's public Client API
(`/public/api/v1/inboxes/{identifier}/contacts/.../messages` with `message_type: "incoming"`),
the same unauthenticated path a real widget/API-channel integration uses. Also found:
`docs/setup.md` assumed the onboarding wizard always creates an inbox; the project owner's real
wizard run didn't, so step 3 now says to check and add one (API channel) if missing.

### Verified, end to end, for real

All three demo scenarios (spam, bug/crash with a KI-014 known-issue match and a grounded draft,
and reporting) were run against the live stack after every fix above -- once through the fully
automated `ai-service` webhook pipeline (with no Claude key, correctly degrading to a safe
human-escalated fallback, which is itself the intended safety behavior), and once by driving
`mcp-server`'s tools directly from this session for real, content-aware classification. The
final `get_support_statistics`/`get_category_statistics` output (7 conversations, 1 spam, 4
human-escalated, category breakdown matching exactly what was tagged) was cross-checked against
what had actually been done to each conversation, not just trusted.

Every fix above shipped with a regression test *and* was confirmed against the real stack after
rebuilding the affected image(s) -- not just re-run against mocks. Test counts: `mcp-server` 17
→ 20, `ai-service` 19 → 21.

### Lesson

Two services' unit test suites, each internally consistent and fully passing, do not prove the
contract *between* them is correct -- five of these six bugs are exactly that class of gap
(payload shape assumptions, replace-vs-merge semantics, exception-hierarchy assumptions) and
every one of them was invisible until both real services and a real Chatwoot were in the loop
together. Reading the actual Rails/Sidekiq logs, and in two cases the Chatwoot image's own
source, settled root causes that would otherwise have been guesswork.

---

## Milestone 3 — Universalized past the game-support framing

**Status:** complete
**Date started:** 2026-08-11
**Date completed:** 2026-08-11

### Decision

The project owner asked to remove all gaming-specific framing: the originating brief was scoped
around a game-support example, and Milestone 0 had already renamed the demo game once ("Ashfall"
→ "Generic") to dodge a real-studio collision, but the whole premise -- game studios, players,
crashes-in-a-dungeon -- was still gaming-flavored throughout. Nothing about the actual
architecture is gaming-specific (Chatwoot, the MCP tool surface, and the classification
workflow don't know or care what kind of product they're supporting), so this was a pure
terminology/content pass, not a redesign.

### What changed

- `game-data/` → `knowledge-base/` (also renamed `patch-notes/` → `release-notes/`), and
  `GAME_DATA_DIR`/`game_data_dir` → `KNOWLEDGE_BASE_DIR`/`knowledge_base_dir` throughout
  `ai-service`, `docker-compose.yml`, and both Dockerfiles.
- The fictional demo dataset changed from a fictional game ("Generic") to a fictional SaaS
  company ("ExampleCo"): the known-issue/draft-response demo scenario changed from "crash
  entering the Cathedral after the third relic" to "crash exporting a report over 10,000 rows,"
  and the sample tickets, FAQ, and release notes were rewritten to match.
- "player" → "customer" throughout code, docs, and prompts (including the classification
  prompt's system framing, "you are triaging a support conversation for a video game" →
  "... for a software product").
- Default `SUPPORT_CATEGORIES` dropped `Gameplay` and added `Feature Request`, a category that
  makes sense for any product, not just games.
- This entry is the only place that narrative change is recorded -- Milestones 0-2 above are
  left exactly as originally written, since they're an accurate record of what was actually true
  and actually tested at the time (including real references to "Ashfall," "Generic," and the
  Cathedral bug). Rewriting history to match current framing would make the journal less useful,
  not more.
- The GitHub repo's description was updated to match; the repo name/URL
  (`ai-game-support-platform`) was intentionally left alone rather than renamed unprompted, since
  a rename breaks any existing clones/links and the project owner didn't ask for that
  specifically -- flagged to them as a follow-up choice.

### Verification

Both test suites re-run clean after the rename (`mcp-server` 20, `ai-service` 21, unchanged
counts -- this was a content pass, not a logic change), and both images were rebuilt and
redeployed against the already-running local stack to confirm the renamed
`knowledge-base/` directory actually lands correctly inside the `ai-service` container
(`docker exec ... ls /app/knowledge-base` showed all four subdirectories) and both services
still report healthy.

---

## Milestone 4 — Postgres backups to S3

**Status:** complete
**Date started:** 2026-08-11
**Date completed:** 2026-08-11

### What was built

A new `backup` service (`backup/`, its own `pyproject.toml`/tests/Dockerfile, mirroring the
`ai-service`/`mcp-server` layout): scheduled `pg_dump -Fc` to S3 via an in-container cron daemon,
a manual-trigger wrapper (`scripts/backup_now.sh`) that runs the literal same script the cron job
runs, and a separate, always-manual `scripts/restore_from_s3.sh` with an interactive confirmation
prompt. Full reasoning in
[ADR 0002](docs/adr/0002-postgres-backup-and-recovery.md). 15 new tests (moto for S3 mocking),
all passing.

### Verified live, against real data, not just mocks

Docker was available, so this was validated for real rather than trusted from unit tests alone:

1. Built the `backup` image and confirmed `docker compose config` accepts the new service.
2. Started a standalone MinIO container (S3-compatible) on the same Compose network.
3. Ran a real backup of the **live Chatwoot database** (the one from Milestone 2's testing --
   real conversations, real tags, real private notes) against that MinIO instance. Confirmed the
   object landed in the bucket.
4. Started a **completely fresh, empty** Postgres container and ran the restore command against
   it, pointed at the same MinIO backup.
5. Confirmed the restored data matched the source exactly: conversation count (7), contact count
   (5), and the literal content of a specific private note (the KI-014 escalation note from
   Milestone 2) byte-for-byte.
6. Separately confirmed the cron daemon itself actually starts and stays running inside the
   container in its normal (non-one-off) mode -- `docker compose up -d backup`, then checked
   `/proc` directly for a live `cron` process (PID 12) alongside the `tail` process keeping the
   container alive, with zero restarts.

This is the same standard applied throughout the project: a documented feature isn't considered
done until it's been run for real, against real data, not just described.

### Notes

- `pg_restore --clean --if-exists --no-owner --no-privileges` was chosen specifically because
  the realistic disaster-recovery scenario is restoring into a *fresh, empty* database (a new VM
  after the old one died) -- `--if-exists` avoids `--clean` reporting spurious errors for DROP
  statements against objects that don't exist yet in an empty target. This worked cleanly in the
  live test above with no error-handling surprises.
- cron's well-known "doesn't inherit the container's env vars" gotcha was handled with
  `declare -p $(compgen -e)` rather than a naive `printenv > file`, specifically so secrets
  containing shell-special characters (a password with a `$` or a quote, say) don't break the
  re-sourced environment. Not separately unit-tested (it's a one-line shell snapshot, not
  application logic), but implicitly covered by the live cron-actually-runs-and-picks-up-real-
  credentials check above -- the real backup in step 3 only succeeded because the cron-invoked
  path (same script, same env-loading mechanism) had working Postgres/S3 credentials.

---

## Milestone 5 — Decoupled AI orchestration: CLI mode and MCP-only/Claude-routine mode

**Status:** complete
**Date started:** 2026-08-11
**Date completed:** 2026-08-11

### What was built

Three ways to run the same classification logic instead of one, per
[ADR 0003](docs/adr/0003-ai-orchestration-deployment-modes.md): `ai-service` moved behind a
Compose profile (`profiles: ["automated"]`) so the bare `docker compose up -d` no longer starts
it -- a deliberate, called-out change from Milestones 1-2's documented default. A new
`ai-service/app/cli.py` (`process` / `process-unprocessed`) reuses
`workflows.classify.process_incoming_message` directly, no parallel logic. Two Claude Code
commands (`.claude/commands/process-support-queue.md`, `support-report.md`) codify the exact
procedure a human already performed manually in Milestone 2, so an MCP-connected session (or a
scheduled Claude routine) can run the whole workflow with no `ai-service` and no Anthropic API
key deployed anywhere.

### Two more real bugs, found by actually running the new CLI against the live stack

1. **`search_conversations` returns a different top-level shape depending on whether a query was
   given.** `GET /conversations/search` (query given) returns `{"meta", "payload"}` at the top
   level; `GET /conversations` (status-only, no query) nests the identical shape under a `"data"`
   key. The CLI's batch sweep only checked for a top-level `"payload"` key, so it silently
   reported "no open conversations found" against a database that had six. Root-caused by
   comparing the raw JSON from both endpoints directly (`curl` against each). Fixed in
   `chatwoot_client.py` by unwrapping the `"data"` key for the no-query path, so both code paths
   return one consistent shape to every caller regardless of which internal Chatwoot endpoint was
   used -- an implementation detail that shouldn't leak through the tool's contract.
2. **The batch sweep used the conversation's overall last message for idempotency, which is
   often the workflow's own note.** After fixing (1), the sweep processed every open conversation
   correctly once -- then processed all of them *again* on the very next run, and would have kept
   doing so forever. Cause: `create_internal_note`/`create_draft_response` each add a new message
   to the conversation, so "the conversation's last message" after a successful run is the AI's
   own note, not the customer message that was actually classified -- comparing that ever-moving
   target against the stored `ai_last_processed_message_id` marker (set to the *customer*
   message's id) could never match. This class of bug couldn't affect the webhook-driven path,
   since Chatwoot's webhook payload always supplies the real triggering message id directly --
   it was specific to the batch sweep's need to *infer* "the latest message" itself. Fixed by
   extracting a shared `get_incoming_messages()` helper (customer messages only, filtered the
   same way the classification prompt itself is built) and using the max id among *those*, not
   the conversation's last message overall. Confirmed live: a second sweep after the fix showed
   `status: skipped, reason: already_processed` for every conversation.

### Verified live

Rebuilt and redeployed `ai-service` and `mcp-server` after each fix (not just re-run against
mocks): `docker exec ... python -m app.cli process-unprocessed` against the real six-conversation
database correctly found and processed all of them once, then correctly skipped all of them on a
second run. Test counts: `mcp-server` 20 → 22, `ai-service` 21 → 26.

### Notes

- The Claude-routine commands are intentionally a *manually-maintained* mirror of
  `claude_client.py`'s prompt/schema, not generated from it (ADR 0003, D6) -- if
  `SUPPORT_CATEGORIES` changes, both need updating by hand. Not yet re-validated live through an
  actual `/process-support-queue` invocation in this milestone (the MCP connector session used
  in Milestone 2 had already disconnected by the time this command was written) -- the command's
  field names and tool call shapes were cross-checked against the real API responses observed
  live during Milestones 2 and 5 instead, but a live run of the command itself remains a good
  follow-up check.

---

## Milestone 6 — Real issue-tracker grounding (Jira, Azure DevOps)

**Status:** complete
**Date started:** 2026-08-11
**Date completed:** 2026-08-11

### Context

The project owner asked directly whether the KI-014 "known issue" match demonstrated in
Milestone 2 was fabricated. Answered honestly: yes — it was this session reading a static
`knowledge-base/known-issues/*.md` fixture file and reasoning about the match itself, not a
query against any real system. Asked for real grounding against an actual Jira and/or Azure
DevOps backlog, and to evaluate implementation approaches first (own Python orchestration,
Anthropic's native MCP connector, Azure Copilot Agents) before building. Full evaluation and
decision in [ADR 0004](docs/adr/0004-issue-tracker-grounding.md) — own orchestration via Python
was chosen; scope confirmed as Jira + Azure DevOps, with the design-doc RAG piece explicitly
deferred.

### What was built

Before writing any integration code, looked up the *actual* tool names each official MCP server
exposes rather than guessing — exactly the kind of fabrication the project owner had just flagged
as a concern. Confirmed via each project's own documentation:
[`searchJiraIssuesUsingJql`](https://github.com/atlassian/atlassian-mcp-server) (Atlassian's
official remote MCP server) and
[`mcp_ado_search_workitem`](https://github.com/microsoft/azure-devops-mcp/blob/main/docs/TOOLSET.md)
(Microsoft's official Azure DevOps MCP server).

`ai-service/app/grounding.py` connects to both as an MCP client (the same `fastmcp.Client`
pattern `mcp_client.py` already uses for `support-mcp-server`), searches using the first customer
message as a short query, and folds real results into `claude_client.py`'s existing prompt
alongside the static knowledge-base excerpt — still one forced Claude tool call, no new agentic
loop. Each source is independently optional and fails independently (a tracker outage degrades to
"no extra context," never a blocked classification). The Claude-routine command
(`process-support-queue.md`) needed no new code for the MCP-only mode — just a note that the same
official servers can be added as connectors there too, since `mcp-server`'s whole design has
always been client-agnostic (ADR 0001).

### Honesty note: this is the one piece not live-verified

Every other feature in this project was run against real infrastructure before being called done.
This one wasn't — no Jira or Azure DevOps credentials were available in this environment. The
tool *names* above are confirmed from official documentation; the exact response *shape* each
tool returns was not independently verified against a live call. `_normalize_jira`/`_normalize_ado`
parse defensively (`.get()` with fallbacks, multiple shape guesses) specifically because of this,
and both the code and [ADR 0004](docs/adr/0004-issue-tracker-grounding.md) say so explicitly
rather than presenting it as verified. What *was* verified: the plumbing around it -- rebuilt and
redeployed `ai-service` with `grounding.py` wired into the live stack (both `*_MCP_URL` vars
unset, matching a real "not configured yet" deployment) and confirmed `python -m app.cli process`
still completes cleanly, proving the integration doesn't break anything when inert. 10 new tests
(mocked MCP responses) cover the normalizers and the independent-failure behavior; ai-service
test count: 26 → 36.

### Follow-up

Real verification against an actual Jira and/or Azure DevOps instance is the natural next step
once credentials are available — treat the first real run as the actual test of
`_normalize_jira`/`_normalize_ado`, and adjust them if a real response shape differs from what's
assumed. The design-doc RAG piece remains deferred (no official MCP server exists for it, unlike
Jira/Azure DevOps, so it would need a real build when picked back up).

---

## Milestone 7 — Confidence honesty check, and a permanent no-auto-send decision

**Status:** complete (documentation/scope decision, no code change)
**Date started:** 2026-08-11
**Date completed:** 2026-08-11

### What happened

While scoping possible next extensions (LinkedIn post drafted first — see the CV/post workflow,
unrelated to the platform itself), the project owner asked directly: is the `confidence` field
real, or was it faked during the Milestone 2 demo like the KI-014 match already admitted to be?

Answered honestly: **`confidence` has always been self-reported by Claude as part of the same
structured tool call that produces `category`/`reason`/`draft_response` — there is no independent
calculation behind it, and there still isn't even with real Jira/Azure DevOps grounding wired in
(Milestone 6). `grounding.py` returns search hits with no similarity/relevance score attached; the
model reads a list of text and self-assesses.** During the live Milestone 2 demo specifically,
those confidence numbers were this session typing plausible values based on its own judgment —
the same category of fabrication as the known-issue match, not something separately verified.

This surfaced a real risk: a "confidence-gated automation" feature (auto-send above some
threshold) was under active discussion as a next extension at the time. Building that on top of
an uncalibrated self-reported number would have been automation safety resting on fabricated
data.

The project owner then stated, independent of the confidence question, that EU legislation
requires either human approval or clear AI-generated labeling before an AI-produced message
reaches a customer, and asked to rule out *any* direct AI-to-customer interface permanently, not
just for now. This closes the confidence-gating question outright: **[ADR 0005](docs/adr/0005-no-direct-ai-to-customer-interface.md)**
records that no confidence score, real or fabricated, will ever authorize an automatic send — the
fix for "confidence isn't real" is surfacing the real signal to the human reviewer, not removing
the human. `README.md`'s Future Extensions and `docs/ai-workflows.md` updated to state this as a
permanent constraint rather than "not in v1."

### Consequences for what's next

"Confidence-gated automation" is removed from consideration entirely. Auto-linking duplicates and
a human-feedback-loop-on-draft-quality remain viable (neither sends anything to the customer). A
real/self-reported confidence split (surfacing actual grounding-match strength to the human
reviewer, never used to bypass them) is still worth building for reviewer speed — proposed, not
yet implemented as of this entry.

---

## Milestone 8 — Knowledge-base RAG (pgvector + fastembed)

**Status:** complete
**Date started:** 2026-08-11
**Date completed:** 2026-08-11

### Context

No Jira/Azure DevOps credentials exist for this portfolio project (confirmed with the project
owner), so the still-deferred design-doc RAG piece from ADR 0004 became the priority instead:
real semantic search over `knowledge-base/`, replacing `knowledge.py`'s flat "dump every file
into every prompt" approach. Asked directly whether pgvector in the same Postgres was the right
call or whether a dedicated/managed vector DB would be better/cheaper/more standard — answered
with a comparison (pgvector already running for Chatwoot itself = zero new infra; dedicated
vector DBs are real infrastructure this project's own scope constraints already rule out at this
corpus size) and a follow-up question on embeddings specifically, since that -- not storage --
was the actual interesting decision. Local embeddings via `fastembed` (zero cost, zero new
vendor) chosen over OpenAI/Voyage AI.

### What was built

`rag-mcp/`, a new self-hosted MCP server (mirrors `mcp-server`'s structure) with three tools:
`search_knowledge_base`, `reindex_knowledge_base`, `index_status`. pgvector lives in its own
`rag` schema of the *same* Postgres instance already running for Chatwoot (no new database
service). Embeddings are `fastembed`'s default model (`BAAI/bge-small-en-v1.5`, 384-dim, ONNX
Runtime), baked into the Docker image at build time rather than downloaded at first use. The
corpus re-indexes fully on every container start (cheap at this scale) plus an on-demand
`reindex_knowledge_base` tool. `ai-service/app/rag_client.py` calls it before building the
classification prompt, falling back to the original flat dump if `RAG_MCP_URL` is unset or the
call fails -- same graceful-degradation pattern as Jira/Azure DevOps grounding and S3 backups.
Unlike those two, `rag-mcp` is wired *on by default* in `docker-compose.yml` (not opt-in) since
it's a local, always-available, zero-cost part of the same stack, not an external vendor
dependency. Full reasoning in
[ADR 0006](docs/adr/0006-knowledge-base-rag.md). 13 new `rag-mcp` tests plus 6 new `ai-service`
tests (rag_client + two prompt-building tests), all passing.

### Verified live at every stage, including real semantic relevance -- not just "it runs"

Before writing any service code: installed `fastembed`/`asyncpg`/`pgvector` for real and ran an
actual embed → insert → cosine-search round trip against the live Chatwoot Postgres (which
already has the `vector` extension from Milestone 1). Real result: a query about "app crashes
exporting a large report" scored 0.92 against the matching known issue and 0.63 against an
unrelated one -- genuine relevance ranking, not just plumbing that doesn't error.

Then, after building the real service: built the actual Docker image (confirming the
build-time model bake works), started it against the real Postgres, and hit a real bug on the
first live tool call — `cannot perform operation: another operation is in progress`. Root cause:
the startup reindex ran via its own `asyncio.run()` call (creating and then closing its own
event loop), while the asyncpg connection pool it created stayed cached in a module global and
was later reused from uvicorn's *different* event loop. Fixed by moving everything -- startup
indexing and the server itself -- inside one `asyncio.run()` call sharing one event loop.
Rebuilt, redeployed, and confirmed two different real queries ranked correctly through the full
stack (HTTP, bearer auth, connection pooling, embeddings, pgvector): the export-crash query
scored the matching known issue 0.800 vs. 0.582 for an unrelated one; a 2FA query correctly
surfaced the FAQ (which covers 2FA) over the unrelated known issues.

Finally, integrated into `ai-service`: rebuilt/redeployed it with the real `rag-mcp` URL wired
in, and called `rag_client.search_knowledge_base` directly inside the running container against
the real live `rag-mcp` service -- got back correctly-ranked, correctly-formatted real content
ready to drop into the classification prompt, confirming the full chain (`ai-service` →
`rag-mcp` → pgvector → fastembed) actually works end to end, not just each piece in isolation.

---
