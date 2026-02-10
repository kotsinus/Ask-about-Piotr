#!/bin/sh

set -eu

_is_truthy() {
  case "${1:-}" in
    1|true|TRUE|yes|YES|on|ON) return 0 ;;
    *) return 1 ;;
  esac
}

AUTO_MIGRATE_ENABLED="${AUTO_MIGRATE_ENABLED:-true}"
AUTO_INGEST_ENABLED="${AUTO_INGEST_ENABLED:-true}"
AUTO_STARTUP_FAIL_FAST="${AUTO_STARTUP_FAIL_FAST:-true}"

echo "[startup] AUTO_MIGRATE_ENABLED=${AUTO_MIGRATE_ENABLED} AUTO_INGEST_ENABLED=${AUTO_INGEST_ENABLED} AUTO_STARTUP_FAIL_FAST=${AUTO_STARTUP_FAIL_FAST}" 1>&2

if _is_truthy "${AUTO_MIGRATE_ENABLED}"; then
  echo "[startup] running DB migrations..." 1>&2
  if ! python scripts/run_migrations.py up; then
    echo "[startup] migrations failed" 1>&2
    if _is_truthy "${AUTO_STARTUP_FAIL_FAST}"; then
      exit 1
    fi
  fi
fi

if _is_truthy "${AUTO_INGEST_ENABLED}"; then
  echo "[startup] ensuring knowledge is ingested..." 1>&2
  if ! python scripts/ensure_ingested.py; then
    echo "[startup] ensure_ingested failed" 1>&2
    if _is_truthy "${AUTO_STARTUP_FAIL_FAST}"; then
      exit 1
    fi
  fi
fi

echo "[startup] starting server: $*" 1>&2
exec "$@"

