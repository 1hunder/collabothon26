#!/bin/sh
# Container entrypoint: migrate, make sure the reference pack is playable, serve.
set -eu

alembic upgrade head

# Seed every curated quest pack (the Quest Board's Guild notices). Idempotent: re-uses the
# existing scenario when a pack is already approved.
python -m financequest refpack seed \
  || echo "WARN: seeding a reference pack failed; continuing" >&2

exec uvicorn financequest.api.main:app \
  --host 0.0.0.0 --port "${PORT:-8000}" \
  --proxy-headers --forwarded-allow-ips='*'
