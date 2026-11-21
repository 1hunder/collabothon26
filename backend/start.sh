#!/bin/sh
# Container entrypoint: migrate, make sure the reference pack is playable, serve.
set -eu

alembic upgrade head

# Idempotent: re-uses the existing scenario when the pack is already approved.
python -m financequest refpack approve financequest/fixtures/reference/fq-av-001 \
  || echo "WARN: reference pack approve failed; continuing" >&2

exec uvicorn financequest.api.main:app \
  --host 0.0.0.0 --port "${PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips='*'
