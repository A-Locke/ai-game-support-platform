# Setup

## Local development

### Prerequisites

- Docker + Docker Compose
- An [Anthropic API key](https://console.anthropic.com/)

### 1. Configure environment

```bash
cp .env.example .env
```

Generate a Chatwoot secret key base and paste it into `.env` as `SECRET_KEY_BASE`:

```bash
openssl rand -hex 64
```

Also generate `MCP_AUTH_TOKEN` the same way (`openssl rand -hex 32` is plenty) and, while you're
at it, `AI_WEBHOOK_SHARED_SECRET` — `mcp-server`'s HTTP transport fails closed (`500`) with no
token configured, so this isn't optional even for local dev. Set `ANTHROPIC_API_KEY`. Everything
else has a working local default.

### 2. Start the stack

```bash
docker compose up -d
```

This starts Postgres, Redis, Chatwoot (web + Sidekiq worker), `mcp-server`, and `ai-service`.
A one-shot `chatwoot-prepare` service runs Chatwoot's database migrations before `chatwoot` and
`chatwoot-sidekiq` start (Chatwoot's image doesn't run migrations on its own — see
[PROJECT_JOURNAL.md, Milestone 1](../PROJECT_JOURNAL.md) if you're curious why). Give it a
minute, then check:

```bash
docker compose ps
curl -I http://localhost:3000/      # Chatwoot -- 302 to the onboarding wizard means it's up
curl http://localhost:8000/health   # ai-service
curl http://localhost:8100/health   # mcp-server
```

### 3. Create the first Chatwoot admin and inbox

Chatwoot's very first admin account can't be created via API (there's no account to
authenticate against yet) — this one step is a manual UI action:

1. Open `http://localhost:3000`, follow the onboarding wizard to create the first
   administrator account. Depending on the wizard flow you're offered, this may or may not
   also create an inbox — verify under **Settings → Inboxes**; if none exists, add one
   (**Add Inbox → API** is the simplest channel type and is what `scripts/run_demo.py` expects).
2. In Chatwoot: click your name at the bottom of the sidebar → **Profile Settings**, then scroll
   down to the **Access Token** section and copy it (this is a different page from Account
   Settings, and the account ID shown there is unrelated to this token).
3. Paste that token into `.env` as `CHATWOOT_API_ACCESS_TOKEN` and
   `MCP_CHATWOOT_API_ACCESS_TOKEN`; set `CHATWOOT_ACCOUNT_ID`/`MCP_CHATWOOT_ACCOUNT_ID` from the
   account id shown on the Account Settings page (also visible in the URL as
   `/app/accounts/<id>/...`).
4. `docker compose up -d mcp-server` to restart it with the token loaded (and `ai-service` too,
   if you're running the fully automated pipeline rather than driving MCP tools by hand).

### 4. Register the webhook, labels, and custom attributes

This step depends on `docker-compose.yml`'s `SAFE_FETCH_ALLOW_PRIVATE_NETWORK=true` on the
Chatwoot services (already set by default) — Chatwoot refuses to deliver webhooks to private-network
hostnames otherwise, which includes every other container on this same Compose network. See the
comment above that env var in `docker-compose.yml`, or PROJECT_JOURNAL.md, Milestone 2, if
you're curious why.

These scripts run on the host (not in a container) and only need `httpx`:

```bash
pip install -r scripts/requirements.txt
python scripts/configure_chatwoot.py
```

This is idempotent — it registers `ai-service`'s webhook URL
(`http://ai-service:8000/webhooks/chatwoot`) for the `message_created` event, creates the
labels used by the AI workflows (`spam`, `human-escalated`, `ai-draft`, plus one per configured
category), and creates the custom attributes `ai_category`, `ai_confidence`, and
`ai_last_processed_message_id`. Only `message_created` is registered, not
`conversation_created` — see [ai-workflows.md](ai-workflows.md#trigger) for why.

### 5. Load the demo scenario

```bash
python scripts/run_demo.py
```

Creates the three demo conversations from `game-data/sample-tickets/` against your local
Chatwoot instance and prints the resulting classification, tags, and any draft response once
`ai-service` has processed them (a few seconds). See the demo scenarios in the [top-level
README](../README.md#demo-scenarios).

## Cloud deployment

Two paths are documented. Both keep Chatwoot on an always-on VM — it needs Postgres, Redis, and
a background worker reachable continuously, which isn't a good serverless fit. They differ in
where `ai-service` and `mcp-server` run.

### Path A (default/simplest): everything on one VM

Matches the brief's preference for minimal infrastructure. Provision the cheapest VM with
~2–4 GB RAM (see [cost-estimate.md](cost-estimate.md) for why 1 GB isn't enough headroom for
Chatwoot itself), install Docker, then:

```bash
git clone <this-repo> && cd <this-repo>
cp .env.example .env   # fill in production values — see below
docker compose -f docker-compose.yml -f deployment/cloud/docker-compose.cloud.yml up -d
```

The cloud override adds a `caddy` service that terminates HTTPS for your domain automatically
(Let's Encrypt, zero manual certificate handling) — point your domain's DNS `A` record at the VM
first, then set `DOMAIN=support.yourdomain.example` in `.env`. `deployment/cloud/Caddyfile`
routes `DOMAIN` to Chatwoot; `ai-service`'s webhook path is only reachable from Chatwoot inside
the Compose network in this path, so it needs no public route at all.

### Path B (optional): MCP server (and/or ai-service) on Google Cloud Run

For pay-per-request economics on the two custom services while Chatwoot stays on the VM. Both
`ai-service` and `mcp-server` are stateless (see
[ADR 0001, D5/D6](adr/0001-architecture-and-tech-stack.md#d6-ai-service-is-also-built-stateless-so-it-can-deploy-the-same-way-as-the-mcp-server))
so either can move independently.

```bash
# mcp-server
gcloud run deploy support-mcp-server \
  --source mcp-server \
  --region <your-region> \
  --no-allow-unauthenticated \
  --set-env-vars MCP_TRANSPORT=streamable-http,MCP_CHATWOOT_BASE_URL=https://support.yourdomain.example,MCP_CHATWOOT_ACCOUNT_ID=1 \
  --set-secrets MCP_CHATWOOT_API_ACCESS_TOKEN=chatwoot-api-token:latest,MCP_AUTH_TOKEN=mcp-auth-token:latest
```

Cloud Run injects `PORT` automatically; the server reads it directly (see
[mcp-server.md](mcp-server.md#transport-and-deployment)). No `min-instances` flag is set, so the
service scales to zero when idle — this is the whole point of the stateless Streamable HTTP
transport (no SSE, no server-side session) chosen in ADR 0001. Point `ai-service`'s
`MCP_SERVER_URL` at the resulting `https://...run.app` URL and its `MCP_AUTH_TOKEN` at the same
secret. `ai-service` can be deployed the same way if desired; Chatwoot's webhook would then need
to reach its public Cloud Run URL directly instead of the Compose-internal address used in
Path A.

### Production environment variables to double-check

- `SECRET_KEY_BASE`, `CHATWOOT_API_ACCESS_TOKEN`, `MCP_AUTH_TOKEN`, `ANTHROPIC_API_KEY` —
  real secrets, never committed (see [.env.example](../.env.example)).
- `MCP_ENABLE_MUTATIONS` — leave `true` for the full demo; set `false` for a read-only/reporting
  deployment.
- `AI_WEBHOOK_SHARED_SECRET` — a shared secret appended as a query parameter to the webhook URL
  registered in Chatwoot, checked by `ai-service` on every inbound webhook request.
