# Build context is the repo root (see docker-compose.yml's build.context for this service) --
# like ai-service, this needs a file outside its own directory: knowledge-base/, the corpus
# it indexes.
FROM python:3.12-slim

WORKDIR /app

COPY rag-mcp/pyproject.toml ./
COPY rag-mcp/app ./app
COPY knowledge-base ./knowledge-base

RUN pip install --no-cache-dir ".[http]"

# Bake the embedding model into the image at build time (docs/adr/0006, D4) -- confirmed live
# that a cold model load takes ~10s; acceptable once at build time, not on every container
# start, and this removes any runtime dependency on Hugging Face Hub being reachable.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding(model_name='BAAI/bge-small-en-v1.5')"

# Both Docker Compose and any cloud deployment use streamable-http -- same reasoning as
# mcp-server's Dockerfile (see docs/mcp-server.md).
ENV RAG_TRANSPORT=streamable-http

EXPOSE 8200

CMD ["python", "-m", "app.server"]
