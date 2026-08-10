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
