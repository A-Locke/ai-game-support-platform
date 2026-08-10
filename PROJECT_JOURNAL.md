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
