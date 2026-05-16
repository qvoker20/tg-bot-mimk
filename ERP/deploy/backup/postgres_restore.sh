#!/usr/bin/env bash
set -euo pipefail

# Usage:
#   DB_NAME=erp DB_USER=postgres DB_HOST=127.0.0.1 DB_PORT=5432 BACKUP_FILE=/path/file.sql.gz ./postgres_restore.sh

DB_NAME="${DB_NAME:-erp}"
DB_USER="${DB_USER:-postgres}"
DB_HOST="${DB_HOST:-127.0.0.1}"
DB_PORT="${DB_PORT:-5432}"
BACKUP_FILE="${BACKUP_FILE:-}"

if [[ -z "$BACKUP_FILE" || ! -f "$BACKUP_FILE" ]]; then
    echo "Set BACKUP_FILE to an existing .sql.gz file"
    exit 1
fi

gunzip -c "$BACKUP_FILE" | psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME"

echo "Restore completed from: $BACKUP_FILE"
