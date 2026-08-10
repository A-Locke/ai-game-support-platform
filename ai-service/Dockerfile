# Build context is the repo root (see docker-compose.yml's build.context for this service) --
# this is the one service that needs a file outside its own directory: the game-data
# knowledge base excerpt used to ground Claude's classification prompt.
FROM python:3.12-slim

WORKDIR /app

COPY ai-service/pyproject.toml ./
COPY ai-service/app ./app
COPY game-data ./game-data

RUN pip install --no-cache-dir .

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
