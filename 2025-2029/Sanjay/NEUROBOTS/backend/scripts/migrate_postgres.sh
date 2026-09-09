#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${NEUROBOTS_DATABASE_URL:-}" ]]; then
  echo "NEUROBOTS_DATABASE_URL must contain the target PostgreSQL connection URL." >&2
  exit 1
fi

case "$NEUROBOTS_DATABASE_URL" in
  postgres://*|postgresql://*|postgresql+psycopg://*) ;;
  *)
    echo "Refusing to migrate a non-PostgreSQL database." >&2
    exit 1
    ;;
esac

.venv/bin/alembic upgrade head
