# Same base image as the postgres service -- guarantees pg_dump/pg_restore match the server's
# major version and understand the vector extension's objects. See docs/adr/0002, D2.
FROM pgvector/pgvector:pg16

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-pip cron \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY app ./app
COPY entrypoint.sh ./

RUN pip3 install --no-cache-dir --break-system-packages . \
    && chmod +x entrypoint.sh

CMD ["./entrypoint.sh"]
