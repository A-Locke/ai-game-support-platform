# Cost Estimate

Approximate monthly cost for the cloud deployment, split by what's driving it. Figures are
ballpark for a low-traffic portfolio/demo deployment (dozens to low hundreds of conversations a
month), not a sized production estimate.

## Path A — everything on one VM (default/recommended)

| Item | Estimate | Why |
|---|---|---|
| VM (2–4 GB RAM, 1–2 vCPU) | **$12–24/mo** | Chatwoot's own docs recommend ≥2 GB RAM for Rails + Sidekiq + Postgres + Redis together; a 1 GB "cheapest tier" VM runs but swaps under load. Reference sizes: Hetzner CX22 (2 vCPU/4 GB, ~€4.2/mo), DigitalOcean/Vultr 2 GB droplet (~$12/mo). |
| Domain (optional) | **$0–12/yr** | Only needed for a real HTTPS hostname; Caddy's automatic HTTPS still works with a free/cheap domain. |
| Storage/bandwidth | **~$0** | Included in most VM plans at this scale. |
| **Infrastructure subtotal** | **~$12–24/mo** | |

## Path B — MCP server (and optionally ai-service) on Cloud Run

| Item | Estimate | Why |
|---|---|---|
| VM (Chatwoot only, 2 GB RAM) | **$10–15/mo** | Slightly smaller than Path A since the two Python services no longer share it. |
| Cloud Run (mcp-server + ai-service) | **$0–2/mo** | Both scale to zero between requests (no SSE/session state to hold open — see [ADR 0001](adr/0001-architecture-and-tech-stack.md)). At demo-scale request volume this stays inside Cloud Run's perpetual free tier (2M requests/month, 360k GB-seconds/month) in practice. |
| **Infrastructure subtotal** | **~$10–17/mo** | Marginally cheaper than Path A at this traffic level; the real benefit is elasticity, not the bill. |

## Claude API usage (both paths)

| Driver | Estimate |
|---|---|
| Classification call per new conversation (~1–2K input tokens incl. knowledge-base context, ~300 output tokens) | Low cents per 100 conversations at current Claude pricing tiers — see [claude.com/pricing](https://claude.com/pricing) for current per-model rates. |
| Reporting summarisation call | Occasional, on-demand only (triggered by a report request, not per-conversation) — negligible at demo volume. |
| **Realistic demo-month estimate** | **< $5/mo** for a few hundred classified conversations plus occasional reports. |

Exact cost depends on which Claude model is configured (`ANTHROPIC_MODEL` in `.env`) and average
conversation length; the classification prompt is deliberately kept short (conversation
messages + a short knowledge-base excerpt, not the whole knowledge base) to keep this line item small
regardless of model choice.

## Support platform cost

**$0.** Chatwoot Community Edition is free, self-hosted, open source — no per-agent or
per-conversation licensing.

## Backups

| Driver | Estimate |
|---|---|
| S3 storage | A `pg_dump -Fc` of a demo-scale Chatwoot database is a few hundred KB to low single-digit MB, compressed. At the default 14-day retention (`BACKUP_RETENTION_DAYS`) and one backup/day, that's well under 100 MB retained — a few cents/month on AWS S3 standard storage, or **$0** on providers with a free tier that covers this (e.g. Cloudflare R2, Backblaze B2's free 10 GB). |
| S3 requests | One `PUT` + a handful of `LIST`/`DELETE` calls per day — negligible, effectively free at any provider's pricing. |

See [ADR 0002](adr/0002-postgres-backup-and-recovery.md) for the backup design; cost only applies
once `S3_BUCKET` is configured — it's opt-in.

## Summed estimate

| Path | Infra | Claude API | Backups | Total |
|---|---|---|---|---|
| A — single VM | $12–24/mo | <$5/mo | ~$0–1/mo | **~$15–30/mo** |
| B — VM + Cloud Run | $10–17/mo | <$5/mo | ~$0–1/mo | **~$15–23/mo** |

## Optional future services (not included above)

If any future extension from the [README's future extensions](../README.md#future-extensions)
is built, budget separately for: a vector database (only if RAG is added — brief explicitly
scopes this out for v1), a managed Postgres tier (if outgrowing the VM's local Postgres), or a
paid domain/SSO product for multi-team access control.
