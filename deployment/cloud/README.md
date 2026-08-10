# Cloud deployment files

See [docs/setup.md](../../docs/setup.md#cloud-deployment) for the full walkthrough (both the
single-VM path and the optional Cloud Run path for `mcp-server`/`ai-service`). This directory
holds only the file assets that walkthrough references:

- `docker-compose.cloud.yml` — overlay adding Caddy (automatic HTTPS) for Path A.
- `Caddyfile` — routes `$DOMAIN` to the `chatwoot` service.
