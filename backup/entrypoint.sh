#!/bin/bash
set -euo pipefail

# cron jobs run in a minimal environment and don't inherit the container's env vars by
# default -- a well-known gotcha. `declare -p` (not a naive `printenv > file`) correctly
# shell-quotes values so secrets containing special characters re-source safely.
declare -p $(compgen -e) > /app/container_env.sh 2>/dev/null || true

SCHEDULE="${BACKUP_CRON_SCHEDULE:-0 3 * * *}"
echo "${SCHEDULE} root . /app/container_env.sh; cd /app && python3 -m app.backup >> /var/log/backup.log 2>&1" > /etc/cron.d/backup
chmod 0644 /etc/cron.d/backup
crontab /etc/cron.d/backup

touch /var/log/backup.log
echo "backup service started -- schedule: ${SCHEDULE}"
cron
# tail as PID 1 keeps the container alive and makes cron's log visible via `docker compose logs`.
exec tail -f /var/log/backup.log
