#!/usr/bin/env bash
set -euo pipefail

if [[ -z "${NEUROBOTS_DATABASE_URL:-}" ]]; then
  echo "NEUROBOTS_DATABASE_URL must contain the target PostgreSQL connection URL." >&2
  exit 1
fi

case "$NEUROBOTS_DATABASE_URL" in
  postgres://*|postgresql://*|postgresql+psycopg://*) ;;
  *)
    echo "Refusing to provision a non-PostgreSQL database." >&2
    exit 1
    ;;
esac

if [[ "$#" -eq 0 ]]; then
  echo "Usage: scripts/provision_postgres.sh --email EMAIL --full-name NAME [--role ROLE]" >&2
  exit 1
fi

scripts/migrate_postgres.sh
.venv/bin/python -m app.create_staff "$@"
