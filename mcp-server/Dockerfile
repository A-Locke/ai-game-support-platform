FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app

RUN pip install --no-cache-dir ".[http]"

# Both Docker Compose and any cloud deployment (including Cloud Run) use streamable-http --
# stdio only makes sense for a developer running this on their own machine. See docs/mcp-server.md.
ENV MCP_TRANSPORT=streamable-http

# Cloud Run injects PORT at runtime; app/server.py reads it via os.environ.get("PORT", ...).
EXPOSE 8100

CMD ["python", "-m", "app.server"]
